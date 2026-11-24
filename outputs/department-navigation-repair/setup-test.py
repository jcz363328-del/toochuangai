from pathlib import Path
root=Path('/tmp/department-navigation-repair')
root.mkdir(exist_ok=True)
for p in Path('/app').iterdir():
    if p.name not in {'app.py','templates','tests','__pycache__','outputs'}:
        dest=root/p.name
        if not dest.exists(): dest.symlink_to(p, target_is_directory=p.is_dir())
(root/'templates').mkdir(exist_ok=True)
for p in Path('/app/templates').iterdir():
    if p.name != 'operation_dept.html':
        dest=root/'templates'/p.name
        if not dest.exists(): dest.symlink_to(p, target_is_directory=p.is_dir())
(root/'tests').mkdir(exist_ok=True)
(root/'tests'/'__init__.py').touch()
