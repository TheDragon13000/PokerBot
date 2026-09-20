const u=new URL("/pyodide/",self.location.origin).href;let a=null,s=null;function r(e){self.postMessage(e)}const c="/engine";async function d(){const e=await(await fetch(`${c}/manifest.json`)).json(),n="/engine_root";for(const o of e.files){const i=await(await fetch(`${c}/${o}`)).text(),t=`${n}/${o}`;a.FS.mkdirTree(t.slice(0,t.lastIndexOf("/"))),a.FS.writeFile(t,i)}a.runPython(`import sys; sys.path.insert(0, "${n}")`),s=a.runPython(`
import json
from poker.game_api import run_level, run_session, human_new, human_deal, human_act

class _Api:
    def run(self, req_json):
        r = json.loads(req_json)
        return json.dumps(run_level(
            opponent=r["opponent"], strategy=r["strategy"], hands=r["hands"],
            seed=r.get("seed"), capture=r.get("capture", 6), config=r.get("config")))
    def run_session(self, req_json):
        r = json.loads(req_json)
        return json.dumps(run_session(
            opponent=r["opponent"], strategy=r["strategy"], stack=r["stack"],
            max_hands=r.get("maxHands", 500), seed=r.get("seed"),
            capture=r.get("capture", 6), config=r.get("config")))
    def human_new(self, req_json):
        r = json.loads(req_json)
        return json.dumps(human_new(
            r["opponents"], seed=r.get("seed"), config=r.get("config"),
            fixed_button=r.get("fixedButton"), stack=r.get("stack"),
            carry=r.get("carry", False)))
    def human_deal(self):
        return json.dumps(human_deal())
    def human_act(self, action):
        return json.dumps(human_act(action))

_Api()
`)}async function g(){r({type:"status",message:"loading Python runtime…"}),a=await(await import(`${u}pyodide.mjs`)).loadPyodide({indexURL:u}),r({type:"status",message:"loading poker engine…"}),await d(),r({type:"ready"})}const l=g().catch(e=>{r({type:"error",message:`Failed to start: ${(e==null?void 0:e.message)??e}`})});function m(e,n){switch(e){case"run":return s.run(JSON.stringify(n));case"run_session":return s.run_session(JSON.stringify(n));case"human_new":return s.human_new(JSON.stringify(n));case"human_deal":return s.human_deal();case"human_act":return s.human_act(n.action);default:throw new Error(`unknown cmd: ${e}`)}}self.onmessage=async e=>{await l;const{id:n,cmd:o,payload:i}=e.data;if(!s){r({id:n,type:"error",message:"engine not ready"});return}try{r({id:n,type:"result",data:JSON.parse(m(o,i))})}catch(t){r({id:n,type:"error",message:(t==null?void 0:t.message)??String(t)})}};
