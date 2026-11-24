from pathlib import Path
p=Path('templates/operation_fba_shipping_methods.html');s=p.read_text(encoding='utf-8')
s=s.replace('</style>','''
.table-wrap{max-height:calc(100dvh - 550px);min-height:360px;overflow:auto}
thead th{position:sticky;top:0;z-index:1;background:#f8fafc}
td:nth-child(4){max-width:190px;overflow:hidden;text-overflow:ellipsis}
td:nth-child(5){max-width:230px;overflow:hidden;text-overflow:ellipsis}
td:nth-child(5) .sub{max-width:230px;overflow:hidden;text-overflow:ellipsis}
.tracking{overflow-wrap:anywhere;white-space:normal}
button:disabled{cursor:default;opacity:.5}
@media(max-width:900px){.table-wrap{max-height:60dvh;min-height:300px}}
</style>''')
s=s.replace('<div class="table-wrap">','<div class="table-wrap" tabindex="0" aria-label="货件列表，可横向及纵向滚动">')
p.write_text(s,encoding='utf-8')
