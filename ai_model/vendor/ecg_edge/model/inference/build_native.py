"""使用已有GCC构建电脑端程序；不调用Vivado、不写板卡。"""
from pathlib import Path
import argparse,subprocess,os,hashlib,json
R=Path(__file__).resolve().parent
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',default='gcc');a=p.parse_args()
    b=R/'bin';b.mkdir(exist_ok=True);s=R/'native';results=[]
    groups={'detector500':['pipeline500.c','rate500.c','classification.c','runtime500_bridge.c','detector_host.c'],'recut500':['recut_host.c']}
    for name,files in groups.items():
        dest=b/(name+('.exe' if os.name=='nt' else ''))
        command=[a.cc,'-std=c11','-O2','-ffp-contract=off','-static-libgcc','-I'+str(s),*[str(s/v) for v in files],'-lm','-o',str(dest)]
        q=subprocess.run(command,capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if q.returncode:raise RuntimeError(q.stderr.decode(errors='replace'))
        results.append(dict(name=name,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),command=command,warnings=q.stderr.decode(errors='replace')))
    (b/'build_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(built=2,host_only=True,board_tested=False),ensure_ascii=False))
if __name__=='__main__':main()
