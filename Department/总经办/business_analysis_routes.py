"""Route handlers for management reporting and business analysis."""

from __future__ import annotations


def business_analysis(
    *,
    _BUSINESS_ANALYSIS_DIST_DIR,
    app,
    os,
    record_business_analysis_usage,
    render_template,
    request,
    send_from_directory,
    session,
):
    """AI 部经营分析看板；页面资源与每日快照均经过主站权限校验。"""
    index_path = os.path.join(_BUSINESS_ANALYSIS_DIST_DIR, 'index.html')
    if not os.path.isfile(index_path):
        return render_template(
            '总经办/business_analysis_unavailable.html',
            reason='经营分析前端资源尚未构建，请联系管理员执行构建。',
        ), 503
    try:
        record_business_analysis_usage(
            user_id=session.get('feishu_user_id'),
            user_name=session.get('feishu_user_name'),
            access_path=request.path,
            client_ip=request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',', 1)[0].strip(),
            user_agent=request.headers.get('User-Agent', ''),
        )
    except Exception:
        app.logger.exception("Failed to record business-analysis usage")
    response = send_from_directory(_BUSINESS_ANALYSIS_DIST_DIR, 'index.html')
    response.headers['Cache-Control'] = 'no-store'
    return response


def business_analysis_asset(
    filename,
    *,
    _BUSINESS_ANALYSIS_DIST_DIR,
    os,
    send_from_directory,
):
    candidates = [filename]
    if not filename.startswith('assets/'):
        candidates.append(f'assets/{filename}')
    for candidate in candidates:
        candidate_path = os.path.join(_BUSINESS_ANALYSIS_DIST_DIR, candidate)
        if os.path.isfile(candidate_path):
            response = send_from_directory(_BUSINESS_ANALYSIS_DIST_DIR, candidate)
            response.headers['Cache-Control'] = 'private, max-age=31536000, immutable'
            return response
    return '', 404


def business_analysis_status(
    *,
    _BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH,
    jsonify,
    os,
):
    ready = os.path.isfile(_BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH)
    return jsonify({
        'ready': ready,
        'snapshot_available': ready,
    })


def business_analysis_dashboard_api(
    *,
    _BUSINESS_ANALYSIS_API_PORT,
    _BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH,
    _BUSINESS_ANALYSIS_SNAPSHOT_PATH,
    _BUSINESS_ANALYSIS_TIER_SNAPSHOT_PATH,
    _ensure_business_analysis_api_started,
    _get_business_analysis_scope,
    _is_business_analysis_api_reachable,
    app,
    datetime,
    force_business_analysis_query_params,
    json,
    jsonify,
    merge_business_analysis_store_tier_snapshot,
    prepare_business_analysis_payload,
    request,
    requests,
    time,
):
    scope = _get_business_analysis_scope(resolve_leader=True)
    if not scope:
        return jsonify({
            'error': {
                'code': 'BUSINESS_ANALYSIS_FORBIDDEN',
                'message': '当前用户不在经营分析五部门范围内。',
            }
        }), 403

    requested_period = str(request.args.get('period') or '').strip()
    try:
        with open(_BUSINESS_ANALYSIS_DASHBOARD_SNAPSHOT_PATH, 'r', encoding='utf-8') as handle:
            dashboard_snapshot = json.load(handle)
        snapshot_period = str(dashboard_snapshot.get('period') or '')
        selected_period = requested_period or snapshot_period
        snapshot_periods = dashboard_snapshot.get('periods')
        snapshot_payload = (
            snapshot_periods.get(selected_period)
            if isinstance(snapshot_periods, dict)
            else None
        )
        if snapshot_payload is None and selected_period == snapshot_period:
            snapshot_payload = dashboard_snapshot.get('envelope')
        if selected_period == snapshot_period and (
            not isinstance(snapshot_payload, dict)
            or not isinstance(snapshot_payload.get('data'), dict)
        ):
            raise ValueError('dashboard snapshot envelope is invalid')
    except (OSError, ValueError) as exc:
        app.logger.error('Business analysis daily snapshot unavailable: %s', exc)
        return jsonify({
            'error': {
                'code': 'DAILY_SNAPSHOT_UNAVAILABLE',
                'message': '每日经营分析快照暂不可用，请等待每日刷新任务完成。',
            }
        }), 503

    # The scheduled snapshot contains the current and previous month. Older
    # periods continue to the live dashboard service below.
    if isinstance(snapshot_payload, dict) and isinstance(snapshot_payload.get('data'), dict):
        payload = prepare_business_analysis_payload(
            snapshot_payload,
            scope,
            selected_period,
        )
        response = jsonify(payload)
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Business-Analysis-Source'] = 'daily-snapshot'
        response.headers['X-Business-Analysis-Period'] = selected_period
        return response

    def category_fallback_for_period(period):
        try:
            with open(_BUSINESS_ANALYSIS_SNAPSHOT_PATH, 'r', encoding='utf-8') as handle:
                snapshot = json.load(handle)
        except (OSError, ValueError) as exc:
            app.logger.warning('Business analysis category fallback unavailable: %s', exc)
            return None
        history = snapshot.get('categorySegmentsByPeriod')
        if isinstance(history, dict) and isinstance(history.get(period), dict):
            return history[period]
        root = snapshot.get('categorySegments')
        return root if isinstance(root, dict) else None

    def needs_category_year_ago(payload):
        data = payload.get('data') if isinstance(payload, dict) else None
        root = data.get('categorySegments') if isinstance(data, dict) else None
        categories = root.get('categories') if isinstance(root, dict) else None
        if not categories:
            return False
        for category in categories:
            if not isinstance(category, dict):
                continue
            company = category.get('company')
            if not isinstance(company, dict) or 'yearAgo' not in company:
                return True
            for row in category.get('departments') or []:
                if isinstance(row, dict) and 'yearAgoSales' not in row:
                    return True
        return False

    def snapshot_response(message):
        # A current-month snapshot must never masquerade as historical data.
        if requested_period and requested_period != snapshot_period:
            return None
        try:
            with open(_BUSINESS_ANALYSIS_SNAPSHOT_PATH, 'r', encoding='utf-8') as handle:
                snapshot_data = json.load(handle)
        except (OSError, ValueError) as exc:
            app.logger.warning('Business analysis snapshot unavailable: %s', exc)
            return None

        try:
            with open(_BUSINESS_ANALYSIS_TIER_SNAPSHOT_PATH, 'r', encoding='utf-8') as handle:
                tier_snapshot = json.load(handle)
            snapshot_data = merge_business_analysis_store_tier_snapshot(
                snapshot_data,
                tier_snapshot,
                warning=message,
            )
        except (OSError, ValueError) as exc:
            app.logger.warning('Business analysis tier snapshot unavailable: %s', exc)
            return None

        extracted_at = str((snapshot_data.get('meta') or {}).get('extractedAt') or '')
        payload = prepare_business_analysis_payload({
            'data': snapshot_data,
            'formulas': [],
            'source': {
                'mode': 'workbook-snapshot',
                'stale': True,
                'fetchedAt': extracted_at or datetime.now().isoformat(),
                'lastSuccessAt': None,
                'latencyMs': None,
                'warning': message,
                'database': {
                    'configured': True,
                    'status': 'down',
                    'latencyMs': None,
                },
            },
            'refreshAfterMs': 60_000,
        }, scope, str(request.args.get('period') or ''))
        response = jsonify(payload)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Business-Analysis-Source'] = 'workbook-snapshot'
        return response

    if not _is_business_analysis_api_reachable(timeout=0.8):
        _ensure_business_analysis_api_started()
        for _ in range(20):
            time.sleep(0.25)
            if _is_business_analysis_api_reachable(timeout=0.5):
                break
        else:
            fallback = snapshot_response('实时数据服务正在启动，当前显示经营数据快照。')
            if fallback is not None:
                return fallback
            return jsonify({
                'error': {
                    'code': 'SERVICE_STARTING',
                    'message': '实时数据服务正在启动，经营数据快照暂不可用。',
                }
            }), 503

    try:
        upstream = requests.get(
            f'http://127.0.0.1:{_BUSINESS_ANALYSIS_API_PORT}/api/dashboard',
            params=force_business_analysis_query_params(
                list(request.args.items(multi=True)),
                scope,
            ),
            timeout=65,
            headers={'Accept': 'application/json'},
        )
    except requests.RequestException:
        fallback = snapshot_response('实时数据服务暂不可用，当前显示经营数据快照。')
        if fallback is not None:
            return fallback
        return jsonify({
            'error': {
                'code': 'SERVICE_UNAVAILABLE',
                'message': '实时数据暂不可用，当前先显示经营数据快照。',
            }
        }), 503

    try:
        payload = upstream.json()
    except ValueError:
        payload = None
    if 200 <= upstream.status_code < 300 and isinstance(payload, dict):
        selected_period = str(request.args.get('period') or '')
        payload = prepare_business_analysis_payload(
            payload,
            scope,
            selected_period,
            category_fallback=(
                category_fallback_for_period(selected_period)
                if needs_category_year_ago(payload)
                else None
            ),
        )
        response = jsonify(payload)
        response.status_code = upstream.status_code
    elif upstream.status_code >= 500:
        fallback = snapshot_response('实时数据库查询失败，当前显示经营数据快照。')
        if fallback is not None:
            return fallback
        response = app.response_class(
            upstream.content,
            status=upstream.status_code,
            content_type=upstream.headers.get('Content-Type', 'application/json; charset=utf-8'),
        )
    else:
        response = app.response_class(
            upstream.content,
            status=upstream.status_code,
            content_type=upstream.headers.get('Content-Type', 'application/json; charset=utf-8'),
        )
    response.headers['Cache-Control'] = 'no-store'
    return response


def business_analysis_scope_api(
    *,
    _get_business_analysis_scope,
    jsonify,
):
    """Return the resolved viewing scope without waiting for dashboard data."""
    scope = _get_business_analysis_scope(resolve_leader=True)
    if not scope:
        return jsonify({
            'error': {
                'code': 'BUSINESS_ANALYSIS_FORBIDDEN',
                'message': 'Current user does not have a resolvable business analysis scope.',
            }
        }), 403
    response = jsonify({'scope': scope})
    response.headers['Cache-Control'] = 'private, max-age=60'
    return response


def _business_analysis_store_tier_scope_condition(
    scope,
    *,
    BUSINESS_ANALYSIS_DEPARTMENT_LEADERS,
):
    """Translate dashboard scope to the actual ownership fields in v_PinPaiDianPu."""
    if not scope or scope.get('role') == 'business_owner':
        return ''
    escape_sql = lambda value: str(value or '').replace("'", "''")
    if scope.get('role') == 'member' and scope.get('operator'):
        return f"LTRIM(RTRIM(dp.YunYing)) = N'{escape_sql(scope['operator'])}'"
    if scope.get('role') == 'department_leader' and scope.get('department'):
        department = str(scope['department']).strip()
        owner_names = set(BUSINESS_ANALYSIS_DEPARTMENT_LEADERS.get(department, set()))
        owner_names.add(department)
        values = ', '.join(f"N'{escape_sql(value)}'" for value in sorted(owner_names))
        return f"LTRIM(RTRIM(dp.BuMen)) IN ({values})"
    return '1 = 0'


def _load_business_analysis_tier_history_snapshot(
    *,
    _BUSINESS_ANALYSIS_TIER_HISTORY_SNAPSHOT_PATH,
    _business_analysis_tier_history_cache,
    _business_analysis_tier_history_cache_lock,
    date,
    detect_promotions,
    json,
    os,
):
    """Load and analyse the snapshot once per file version, not once per request."""
    stat = os.stat(_BUSINESS_ANALYSIS_TIER_HISTORY_SNAPSHOT_PATH)
    with _business_analysis_tier_history_cache_lock:
        cached = _business_analysis_tier_history_cache
        if cached['mtime_ns'] == stat.st_mtime_ns and cached['snapshot'] is not None:
            return cached['snapshot'], cached['promotion_events']
        with open(_BUSINESS_ANALYSIS_TIER_HISTORY_SNAPSHOT_PATH, 'r', encoding='utf-8') as handle:
            snapshot = json.load(handle)
        snapshot_rows = snapshot.get('rows')
        if not isinstance(snapshot_rows, list):
            raise ValueError('tier history snapshot rows are invalid')
        saved_events = snapshot.get('promotionEvents')
        if isinstance(saved_events, list):
            promotion_events = [type('SnapshotPromotionEvent', (), {
                'store': int(item.get('store')),
                'tier': str(item.get('tier') or ''),
                'tier_rank': int(item.get('tierRank') or 0),
                'qualified_on': date.fromisoformat(str(item.get('qualifiedOn'))[:10]),
            }) for item in saved_events if isinstance(item, dict)]
        else:
            promotion_rows = [
                (item.get('date'), item.get('store'), item.get('tier'), item.get('tierRank'))
                for item in snapshot_rows
                if isinstance(item, dict) and item.get('tierRank') is not None
            ]
            promotion_events = detect_promotions(promotion_rows)
        cached.update({
            'mtime_ns': stat.st_mtime_ns,
            'snapshot': snapshot,
            'promotion_events': promotion_events,
        })
        return snapshot, promotion_events


def business_analysis_store_tier_history_api(
    *,
    BUSINESS_ANALYSIS_DEPARTMENT_LEADERS,
    _BUSINESS_ANALYSIS_ROOT,
    _get_business_analysis_scope,
    _load_business_analysis_tier_history_snapshot,
    app,
    date,
    json,
    jsonify,
    os,
    request,
    timedelta,
):
    """Return the daily tier-history snapshot constrained to the viewer scope."""
    scope = _get_business_analysis_scope(resolve_leader=True)
    if not scope or scope.get('role') == 'ratio_viewer':
        return jsonify({'rows': [], 'total': 0})

    raw_store = str(request.args.get('store') or '').strip()
    store = None
    if raw_store:
        try:
            store = int(raw_store)
        except ValueError:
            return jsonify({'error': {'code': 'INVALID_STORE', 'message': '店铺参数无效'}}), 400
        if store <= 0:
            return jsonify({'error': {'code': 'INVALID_STORE', 'message': '店铺参数无效'}}), 400
    try:
        days = int(request.args.get('days') or 90)
    except (TypeError, ValueError):
        return jsonify({'error': {'code': 'INVALID_DAYS', 'message': '日期范围参数无效'}}), 400
    if days not in {30, 90, 180, 365}:
        return jsonify({'error': {'code': 'INVALID_DAYS', 'message': '日期范围仅支持 30、90、180、365 天'}}), 400

    try:
        snapshot, promotion_events = _load_business_analysis_tier_history_snapshot()
        snapshot_rows = snapshot.get('rows')
        max_date_text = str(snapshot.get('maxDate') or '')[:10]
        max_date = date.fromisoformat(max_date_text)
    except (OSError, ValueError, TypeError) as exc:
        app.logger.error('Business analysis store-tier history snapshot unavailable: %s', exc)
        return jsonify({'error': {
            'code': 'STORE_TIER_HISTORY_SNAPSHOT_UNAVAILABLE',
            'message': '店铺等级历史快照暂不可用，请等待每日刷新任务完成。',
        }}), 503

    allowed_departments = set()
    if scope.get('role') == 'department_leader' and scope.get('department'):
        department = str(scope['department']).strip()
        allowed_departments.update(BUSINESS_ANALYSIS_DEPARTMENT_LEADERS.get(department, set()))
        allowed_departments.add(department)

    def is_visible(item):
        if scope.get('role') == 'business_owner':
            return True
        if scope.get('role') == 'member' and scope.get('operator'):
            return str(item.get('operator') or '').strip() == str(scope['operator']).strip()
        if scope.get('role') == 'department_leader':
            return str(item.get('department') or '').strip() in allowed_departments
        return False

    scoped_rows = [item for item in snapshot_rows if isinstance(item, dict) and is_visible(item)]
    if store is not None:
        scoped_rows = [item for item in scoped_rows if int(item.get('store') or 0) == store]
    start_date = max_date - timedelta(days=days - 1)
    payload = [item for item in scoped_rows if str(item.get('date') or '')[:10] >= start_date.isoformat()]
    payload.sort(key=lambda item: (str(item.get('date') or ''), int(item.get('store') or 0)), reverse=True)
    history_rows = [
        (item.get('date'), item.get('store'), item.get('tier'), item.get('tierRank'))
        for item in scoped_rows
        if item.get('tierRank') is not None
    ]
    by_store = {}
    for raw_day, raw_store, raw_tier, raw_rank in history_rows:
        by_store.setdefault(int(raw_store), []).append({
            'date': raw_day if isinstance(raw_day, date) else date.fromisoformat(str(raw_day)[:10]),
            'tier': str(raw_tier or ''),
            'rank': int(raw_rank) if raw_rank is not None else 0,
        })
    official_by_store = {}
    official_baseline_path = os.path.join(
        _BUSINESS_ANALYSIS_ROOT,
        'data',
        'store-tier-official-baseline.json',
    )
    try:
        with open(official_baseline_path, 'r', encoding='utf-8') as handle:
            baseline_stores = (json.load(handle) or {}).get('stores') or {}
        for raw_store, item in baseline_stores.items():
            if not isinstance(item, dict):
                continue
            official_by_store[int(raw_store)] = {
                'historicalOfficialTier': str(item.get('tier') or ''),
                'historicalOfficialTierRank': int(item.get('tierRank') or 0),
                'officialSince': str(item.get('officialSince') or '') or None,
                'officialSource': '历史正式晋级台账',
            }
    except (OSError, ValueError, TypeError) as exc:
        app.logger.warning('Store tier official baseline unavailable: %s', exc)
    visible_store_ids = set(by_store)
    for event in promotion_events:
        if event.store not in visible_store_ids:
            continue
        current = official_by_store.get(event.store)
        if current is None or event.tier_rank > current['historicalOfficialTierRank']:
            official_by_store[event.store] = {
                'historicalOfficialTier': event.tier,
                'historicalOfficialTierRank': event.tier_rank,
                'officialSince': event.qualified_on.isoformat(),
                'officialSource': '每日快照连续30天确认',
            }
    store_meta = []
    for store_id, history in sorted(by_store.items()):
        history.sort(key=lambda item: item['date'])
        latest = history[-1]
        current_level_days = 0
        expected_day = latest['date']
        for item in reversed(history):
            if item['date'] != expected_day or item['tier'] != latest['tier']:
                break
            current_level_days += 1
            expected_day -= timedelta(days=1)
        store_meta.append({
            'store': store_id,
            'currentTier': latest['tier'],
            'currentLevelDays': current_level_days,
            **official_by_store.get(store_id, {
                'historicalOfficialTier': None,
                'historicalOfficialTierRank': None,
                'officialSince': None,
                'officialSource': None,
            }),
        })
    response = jsonify({
        'rows': payload,
        'storeMeta': store_meta,
        'total': len(payload),
        'days': days,
        'source': 'daily-snapshot',
        'generatedAt': snapshot.get('generatedAt'),
    })
    response.headers['Cache-Control'] = 'private, max-age=300'
    response.headers['X-Business-Analysis-Source'] = 'daily-snapshot'
    return response


def business_analysis_promotion_backfill_api(
    *,
    _get_business_analysis_scope,
    app,
    date,
    jsonify,
    request,
    timedelta,
):
    scope = _get_business_analysis_scope(resolve_leader=True)
    if not scope or scope.get('role') != 'business_owner':
        return jsonify({'error': {'message': '仅经营负责人可补发晋级通知'}}), 403
    from Department.总经办.business_analysis_promotion_backfill import preview_backfill, send_backfill
    try:
        if request.method == 'POST':
            # Require a same-origin JSON request for this session-authenticated write.
            if not request.is_json or (request.headers.get('Origin') and
                    request.headers['Origin'].rstrip('/') != request.host_url.rstrip('/')):
                return jsonify({'error': {'message': '请从经营分析页面提交补发'}}), 403
            body = request.get_json(silent=True) or {}
            record_id = body.get('recordId')
            if type(record_id) is not int or record_id <= 0:
                raise ValueError('晋级记录参数无效')
            result = send_backfill(record_id)
        else:
            end = date.fromisoformat(request.args.get('end') or date.today().isoformat())
            start = date.fromisoformat(request.args.get('start') or (end - timedelta(days=89)).isoformat())
            if start > end or (end - start).days > 365:
                raise ValueError('请选择不超过366天的有效日期范围')
            raw_store = request.args.get('store', '').strip()
            store = int(raw_store) if raw_store else None
            if store is not None and store <= 0:
                raise ValueError('店铺参数无效')
            result = preview_backfill(start, end, store)
        response = jsonify(result)
        response.headers['Cache-Control'] = 'no-store'
        return response
    except ValueError as exc:
        return jsonify({'error': {'message': str(exc)}}), 400
    except Exception:
        app.logger.exception('Promotion backfill failed')
        return jsonify({'error': {'message': '补发服务暂不可用，请刷新记录核对发送状态后重试'}}), 503


def business_analysis_fiscal_overview_api(
    *,
    _get_business_analysis_scope,
    app,
    jsonify,
    load_fiscal_overview,
    request,
    validate_fiscal_year,
):
    """返回按当前经营分析权限裁剪后的财年目标达成首页数据。"""
    scope = _get_business_analysis_scope(resolve_leader=True)
    if not scope:
        return jsonify({
            'error': {
                'code': 'BUSINESS_ANALYSIS_FORBIDDEN',
                'message': '当前用户无权访问经营分析财年首页。',
            }
        }), 403

    try:
        fiscal_year = validate_fiscal_year(request.args.get('fiscal_year') or '2026-2027')
        force_value = str(request.args.get('force') or '0').strip().lower()
        if force_value not in {'0', '1', 'false', 'true'}:
            raise ValueError('force 参数仅支持 0、1、false 或 true')
        payload = load_fiscal_overview(
            fiscal_year,
            scope,
            force=force_value in {'1', 'true'},
            filters={
                'department': request.args.get('department'),
                'periodType': request.args.get('period_type') or 'annual',
                'period': request.args.get('period'),
            },
        )
    except ValueError as exc:
        return jsonify({
            'error': {
                'code': 'INVALID_FISCAL_OVERVIEW_QUERY',
                'message': str(exc),
            }
        }), 400
    except Exception as exc:
        app.logger.exception('business analysis fiscal overview failed: %s', exc)
        return jsonify({
            'error': {
                'code': 'FISCAL_OVERVIEW_UNAVAILABLE',
                'message': '财年目标数据暂时无法读取，请稍后重试。',
            }
        }), 503

    response = jsonify(payload)
    response.headers['Cache-Control'] = 'no-store'
    return response


def business_analysis_key_tasks_api(
    task_id,
    *,
    KeyTaskStoreError,
    _business_analysis_key_task_store,
    _get_business_analysis_scope,
    app,
    jsonify,
    request,
):
    """读写经营分析关键任务；内容由本地服务直接持久化为 JSON。"""
    scope = _get_business_analysis_scope(resolve_leader=True)
    if not scope:
        return jsonify({
            'error': {
                'code': 'BUSINESS_ANALYSIS_FORBIDDEN',
                'message': '当前用户无权访问经营分析关键任务。',
            }
        }), 403

    try:
        if request.method == 'GET':
            payload = _business_analysis_key_task_store.list(scope)
        elif request.method == 'POST':
            payload = _business_analysis_key_task_store.create(request.get_json(silent=True), scope)
        elif request.method == 'PUT':
            payload = _business_analysis_key_task_store.update(
                str(task_id or ''),
                request.get_json(silent=True),
                scope,
            )
        else:
            payload = _business_analysis_key_task_store.remove(str(task_id or ''), scope)
    except KeyTaskStoreError as exc:
        return jsonify({
            'error': {
                'code': exc.code,
                'message': exc.message,
            }
        }), exc.status
    except OSError as exc:
        app.logger.exception('Failed to persist business analysis key tasks: %s', exc)
        return jsonify({
            'error': {
                'code': 'TASK_FILE_UNAVAILABLE',
                'message': '关键任务 JSON 文件暂时无法读写，请稍后重试。',
            }
        }), 503

    response = jsonify(payload)
    response.headers['Cache-Control'] = 'no-store'
    return response


def _company_market_full_access_guard(
    *,
    _get_business_analysis_scope,
    jsonify,
):
    """美国站市场与大盘对比只对拥有经营分析全量数据权限的人开放。"""
    scope = _get_business_analysis_scope(resolve_leader=True)
    if not scope:
        return jsonify({
            'error': {
                'code': 'BUSINESS_ANALYSIS_FORBIDDEN',
                'message': '当前用户无权访问经营分析。',
            }
        }), 403
    if str(scope.get('role') or '') != 'business_owner':
        return jsonify({
            'error': {
                'code': 'COMPANY_MARKET_FORBIDDEN',
                'message': '美国站市场与大盘对比只对拥有经营分析全量数据权限的用户开放。',
            }
        }), 403
    return None


def business_analysis_market_overview_api(
    *,
    CompanyMarketError,
    app,
    get_market_overview_rows,
    jsonify,
):
    """大盘趋势：返回美国站市场录入的类目销量/销售额（全体经营分析用户可见）。"""
    try:
        rows = get_market_overview_rows()
    except CompanyMarketError as exc:
        return jsonify({'error': {'code': exc.code, 'message': exc.message}}), exc.status
    except Exception as exc:
        app.logger.exception('market overview failed: %s', exc)
        return jsonify({
            'error': {
                'code': 'MARKET_OVERVIEW_UNAVAILABLE',
                'message': '大盘趋势数据暂时无法读取，请稍后重试。',
            }
        }), 503
    response = jsonify({'rows': rows})
    response.headers['Cache-Control'] = 'no-store'
    return response


def business_analysis_company_market_api(
    *,
    CompanyMarketError,
    _company_market_full_access_guard,
    app,
    get_company_market_overview,
    jsonify,
    request,
):
    """返回手动导入的美国站市场与大盘对比数据（按月份）。"""
    denied = _company_market_full_access_guard()
    if denied is not None:
        return denied
    try:
        payload = get_company_market_overview(request.args.get('month') or None)
    except CompanyMarketError as exc:
        return jsonify({'error': {'code': exc.code, 'message': exc.message}}), exc.status
    except Exception as exc:
        app.logger.exception('company market overview failed: %s', exc)
        return jsonify({
            'error': {
                'code': 'COMPANY_MARKET_UNAVAILABLE',
                'message': '公司大盘数据暂时无法读取，请稍后重试。',
            }
        }), 503
    payload['canEdit'] = True
    response = jsonify(payload)
    response.headers['Cache-Control'] = 'no-store'
    return response


def business_analysis_company_market_entry_api(
    *,
    CompanyMarketError,
    _company_market_full_access_guard,
    app,
    jsonify,
    request,
    upsert_company_market_month,
):
    """按月手动录入/覆盖美国站市场与大盘对比数据。"""
    denied = _company_market_full_access_guard()
    if denied is not None:
        return denied
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({
            'error': {
                'code': 'COMPANY_MARKET_INVALID_VALUES',
                'message': '提交的数据格式不正确。',
            }
        }), 400
    try:
        payload = upsert_company_market_month(
            body.get('month'),
            body.get('values'),
            body.get('date'),
        )
    except CompanyMarketError as exc:
        return jsonify({'error': {'code': exc.code, 'message': exc.message}}), exc.status
    except Exception as exc:
        app.logger.exception('company market entry failed: %s', exc)
        return jsonify({
            'error': {
                'code': 'COMPANY_MARKET_ENTRY_FAILED',
                'message': f'保存失败：{exc}',
            }
        }), 503
    payload['canEdit'] = True
    response = jsonify(payload)
    response.headers['Cache-Control'] = 'no-store'
    return response
