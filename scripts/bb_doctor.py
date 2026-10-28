#!/usr/bin/env python3
"""Read-only live diagnosis; no config write, installation or process restart."""
import argparse
import json
from pathlib import Path
from bb_client import Client, structured
from item_common import write_new

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',default='http://localhost:3000/bb-mcp');p.add_argument('--output',type=Path)
    a=p.parse_args()
    try:
        with Client(a.url) as c:
            catalog=c.call('tools/list',{});names={x['name'] for x in catalog.get('tools',[])}
            report={'connected':True,'server':c.info.get('serverInfo'),'tool_count_current_page':len(names),'catalog_has_more':bool(catalog.get('nextCursor'))}
            if 'get_capabilities' in names:
                caps=structured(c.tool('get_capabilities',{'include_tools':True}))
                report.update(blockbench=caps.get('blockbench'),plugin=caps.get('plugin'),project=caps.get('project'),format=caps.get('format'))
                report['currently_disabled_tools']=[t['name'] for t in caps.get('tools',[]) if not t.get('enabled')]
            else:report['limitation']='get_capabilities unavailable; upgrade only after checking installed plugin source/version'
            report['notes']=['No project is a valid connected state','Disabled tools may be mode/format dependent','Editor capability does not certify game compatibility']
    except Exception as exc:report={'connected':False,'error_type':type(exc).__name__,'error':str(exc)[:1500]}
    if a.output:write_new(a.output,report)
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['connected'] else 1

if __name__=='__main__':raise SystemExit(main())
