FROM toochuangai-single:special-permissions-20261117
COPY innovation_blueprint.py /app/innovation_blueprint.py
COPY innovation/ /app/innovation/
RUN /opt/web/bin/python -m py_compile /app/innovation_blueprint.py /app/innovation/specials.py /app/innovation/special_support.py

