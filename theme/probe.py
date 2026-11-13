"""헤드리스 검증용 페이지 생성: python3 theme/probe.py <outdir>"""
import re, sys
src = open('server.py', encoding='utf-8').read()
P = eval('"""' + re.search(r'PORTAL_HTML = """(.*?)\n"""', src, re.S).group(1) + '"""')
def mk(name, stage, fs, hop=None, detail=False):
    js = '''<script>window.__errs=[];window.addEventListener('error',e=>__errs.push(e.message+' @'+e.lineno));
setTimeout(()=>{try{switchTab('dr')}catch(e){__errs.push('tab:'+e.message)}},200);
function go(){ if(!window.Topo2D){return setTimeout(go,200);}
 for(const k of ['normal','l1','l2','path','l3','l4','bs','surge','mgmt']){try{setV3Stage(k)}catch(e){__errs.push(k+':'+e.message)}}
 setV3Stage('%s');
 const c=document.getElementById('dr-console');
 if(%s){c.classList.add('is-fs');syncDrFsBtn();} else {document.getElementById('dr-panel').scrollTop=c.offsetTop-12;}
 if(%s){toggleDrDetail(true);}
 %s
 document.body.setAttribute('data-probe',JSON.stringify({errs:__errs,flow:document.querySelectorAll('#dc-flow li').length,title:document.getElementById('v3-stage-title').innerText.slice(0,30),has2d:document.querySelector('.iso-stage').classList.contains('has-2d')}));}
setTimeout(go,400);</script></body>''' % (stage, 'true' if fs else 'false', 'true' if detail else 'false',
        ('document.querySelector(".t3-bar [data-k=play]").click();' + 'for(let i=0;i<%d;i++)document.querySelector(".t3-bar [data-k=next]").click();' % hop) if hop is not None else '')
    open('%s/%s.html' % (sys.argv[1], name), 'w').write(P.replace('</body>', js))
mk('u_normal', 'normal', False, hop=9)
mk('u_fs_surge', 'surge', True, hop=4)
mk('u_fs_mgmt', 'mgmt', True, hop=6)
mk('u_fs_normal', 'normal', True, hop=12)
