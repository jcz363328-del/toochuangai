def load_points_leaderboard(query):
    rows = query("""
        SELECT TOP 20 LTRIM(RTRIM(发起人)) AS 姓名,
            SUM(COALESCE(最高分, 0)) AS 累计积分
        FROM v_quanyuanchuangxin
        WHERE 最高分 > 0 AND NULLIF(LTRIM(RTRIM(发起人)), '') IS NOT NULL
        GROUP BY LTRIM(RTRIM(发起人))
        ORDER BY 累计积分 DESC, 姓名 ASC
    """) or []
    leaders = []
    previous_score = None
    rank = 0
    for position, row in enumerate(rows[:20], start=1):
        name, score = str(row[0]), float(row[1] or 0)
        if score != previous_score:
            rank = position
        previous_score = score
        tier = 'gold' if rank == 1 else 'silver' if rank == 2 else 'bronze' if rank == 3 else 'diamond' if rank <= 10 else 'rising'
        labels = {'gold': '创新领航者', 'silver': '创新先锋', 'bronze': '创新能手', 'diamond': '创新精英', 'rising': '创新新锐'}
        leaders.append({'rank': rank, 'name': name, 'score': score, 'tier': tier, 'tier_label': labels[tier]})
    return leaders
