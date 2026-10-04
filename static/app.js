const $ = (q) => document.querySelector(q);
const state = { token: "", files: [], selected: new Set(), busy: false, publicMode: false, authenticated: false };
const esc = (value) => String(value).replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const headers = (body) => {
  const result = {};
  if (!(body instanceof FormData)) result["Content-Type"] = "application/json";
  if (!state.publicMode && state.token) result["X-Local-Session"] = state.token;
  return result;
};
let toastTimer;
function toast(message){const el=$("#toast");el.textContent=message;el.classList.add("show");clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove("show"),2600)}
async function api(url, options={}){
  const response=await fetch(url,{...options,credentials:"same-origin",headers:{...headers(options.body),...(options.headers||{})}});
  const data=await response.json().catch(()=>({detail:"服务器返回了无法识别的响应"}));
  if(!response.ok) throw new Error(data.detail||`请求失败 (${response.status})`);
  return data;
}
function updateComposer(){const enabled=Boolean(state.files.length)&&!state.busy;$("#prompt").disabled=!enabled;$("#sendBtn").disabled=!enabled;}
function renderFiles(){
  const term=$("#fileSearch").value.trim().toLowerCase();
  const visible=state.files.filter(p=>p.toLowerCase().includes(term));
  $("#fileCount").textContent=`${state.selected.size} 已选`;
  const host=$("#fileList");
  if(!state.files.length){host.innerHTML='<div class="empty-files">选择一个文件夹<br>开始浏览项目</div>';return;}
  if(!visible.length){host.innerHTML='<div class="empty-files">没有匹配的文件</div>';return;}
  host.innerHTML=visible.map(path=>{
    const selected=state.selected.has(path);const name=path.split("/").pop();const folder=path.includes("/")?path.slice(0,path.lastIndexOf("/")):"";
    const ext=name.includes(".")?name.split(".").pop().slice(0,3).toUpperCase():"TXT";
    return `<div class="file-row ${selected?"selected":""}" data-path="${esc(path)}" title="${esc(path)}"><span class="file-check">${selected?"✓":""}</span><span class="file-icon">${esc(ext)}</span><span class="file-name">${folder?`<span style="color:#a5aaa1">${esc(folder)}/</span>`:""}${esc(name)}</span></div>`;
  }).join("");
}
function setWorkspace(path, files){
  state.files=files;state.selected=new Set();
  $("#workspacePath").textContent=path||"已隔离的项目工作区";$("#workspacePath").title=path||"已隔离的项目工作区";
  $("#projectName").textContent=(path||"项目").split(/[\\/]/).filter(Boolean).pop()||"项目";
  $("#welcome").style.display="block";renderFiles();updateComposer();
  toast(`已载入 ${files.length} 个可用文本文件`);
}
$("#fileList").addEventListener("click",e=>{
  const row=e.target.closest(".file-row");if(!row)return;
  const path=row.dataset.path;
  if(state.selected.has(path))state.selected.delete(path);else state.selected.add(path);
  renderFiles();
});
$("#fileSearch").addEventListener("input",renderFiles);
$("#chooseFolder").addEventListener("click",async()=>{
  if(state.publicMode){$("#projectZip").click();return;}
  try{const data=await api("/api/pick-folder",{method:"POST",body:"{}"});if(!data.cancelled)setWorkspace(data.path,data.files);}
  catch(err){toast(err.message)}
});
$("#projectZip").addEventListener("change",async(event)=>{
  const file=event.target.files?.[0];if(!file)return;
  const button=$("#chooseFolder");button.disabled=true;button.innerHTML="<span>…</span> 正在安全导入";
  const form=new FormData();form.append("file",file);
  try{const data=await api("/api/workspace/upload",{method:"POST",body:form});setWorkspace(data.path,data.files);}
  catch(err){toast(err.message)}
  finally{button.disabled=false;button.innerHTML="<span>＋</span> 上传项目 ZIP";event.target.value="";}
});
$("#accountButton").addEventListener("click",async()=>{
  if(!state.publicMode)return;
  if(!state.authenticated)return;
  if(confirm("退出当前账号？")){
    try{await api("/api/auth/logout",{method:"POST",body:"{}"});location.reload();}
    catch(err){toast(err.message)}
  }
});
async function submitAuth(register=false){
  const email=$("#authEmail").value.trim(),password=$("#authPassword").value;
  const submit=$("#authSubmit"),error=$("#authError");
  error.textContent="";submit.disabled=true;submit.textContent=register?"正在创建…":"正在登录…";
  try{
    const data=await api(register?"/api/auth/register":"/api/auth/login",{method:"POST",body:JSON.stringify({email,password})});
    if(data.confirmation_required){error.textContent=data.message;return;}
    location.reload();
  }catch(err){error.textContent=err.message;}
  finally{submit.disabled=false;submit.textContent="登录";}
}
$("#authForm").addEventListener("submit",e=>{e.preventDefault();submitAuth(false);});
$("#registerButton").addEventListener("click",()=>submitAuth(true));
function showApiKeyStatus(settings){
  const status=$("#apiKeyStatus");
  if(!settings.api_key_configured){status.textContent="尚未配置。填写你自己的 Key 后保存到本机。";return;}
  status.textContent=settings.api_key_source==="environment"
    ?"已从 DEEPSEEK_API_KEY 环境变量读取。"
    :"已保存在本机用户配置目录中，不会提交到 GitHub。";
}
async function refreshLocalSettings(){
  const settings=await api("/api/settings");
  $("#settingsModel").textContent=settings.model||"deepseek-flash";
  showApiKeyStatus(settings);
}
async function saveApiKey(){
  const input=$("#deepseekApiKey"),button=$("#saveApiKey"),key=input.value.trim();
  if(!key){$("#apiKeyStatus").textContent="请先粘贴 DeepSeek API Key。";input.focus();return;}
  button.disabled=true;button.textContent="保存中…";
  try{
    const settings=await api("/api/settings",{method:"POST",body:JSON.stringify({deepseek_api_key:key})});
    input.value="";$("#settingsModel").textContent=settings.model||"deepseek-flash";showApiKeyStatus(settings);
    toast("API Key 已保存在本机");
  }catch(err){$("#apiKeyStatus").textContent=err.message;}
  finally{button.disabled=false;button.textContent="保存";}
}
$("#settingsForm").addEventListener("submit",event=>{event.preventDefault();saveApiKey();});
$("#saveApiKey").addEventListener("click",saveApiKey);
$("#settingsClose").addEventListener("click",()=>$("#settingsDialog").close());
$("#settingsDone").addEventListener("click",()=>$("#settingsDialog").close());
$("#settingsBtn").addEventListener("click",async()=>{
  $("#settingsDialog").showModal();
  if(state.publicMode){
    $("#localApiSettings").hidden=true;
    $("#settingsDescription").textContent="云端部署使用服务器环境变量中的 DeepSeek API Key。";
    return;
  }
  $("#localApiSettings").hidden=false;
  try{await refreshLocalSettings();}catch(err){$("#apiKeyStatus").textContent=err.message;}
});
$("#newChat").addEventListener("click",()=>{$("#messages").innerHTML="";$("#messages").classList.remove("active");$("#welcome").style.display="block";$("#prompt").value="";});
$(".suggestions").addEventListener("click",e=>{const btn=e.target.closest(".suggestion");if(btn){$("#prompt").value=btn.dataset.prompt;$("#prompt").focus();resizeInput();}});
function resizeInput(){const el=$("#prompt");el.style.height="auto";el.style.height=Math.min(el.scrollHeight,130)+"px";}
$("#prompt").addEventListener("input",resizeInput);
function showMessage(role,text){
  const messages=$("#messages");messages.classList.add("active");$("#welcome").style.display="none";
  const el=document.createElement("div");el.className="message";
  if(role==="user"){el.innerHTML=`<div class="user-message">${esc(text)}</div>`;}
  else{el.innerHTML=`<div class="assistant-label">栈灯 · 助手</div><div class="assistant-message">${esc(text)}</div>`;}
  messages.append(el);messages.scrollTop=messages.scrollHeight;return el;
}
function diffHtml(diff){return esc(diff||"（没有文本差异）").split("\n").map(line=>{
  if(line.startsWith("+"))return `<span class="plus">${line}</span>`;
  if(line.startsWith("-"))return `<span class="minus">${line}</span>`;
  return line;
}).join("\n");}
function addEdits(host,edits){
  for(const edit of edits){
    const card=document.createElement("div");card.className="edit-card";
    card.innerHTML=`<div class="edit-head"><span class="file-icon">EDIT</span><span>${esc(edit.path)}</span><small>待审阅</small></div><pre class="diff">${diffHtml(edit.diff)}</pre><div class="edit-actions"><button class="discard">忽略</button><button class="apply">应用修改</button></div>`;
    card.querySelector(".discard").addEventListener("click",()=>card.remove());
    card.querySelector(".apply").addEventListener("click",async(event)=>{
      const button=event.currentTarget;button.disabled=true;button.textContent="应用中…";
      try{await api("/api/apply",{method:"POST",body:JSON.stringify({path:edit.path,content:edit.content,expected_hash:edit.hash})});card.innerHTML=`<div class="edit-head"><span class="file-icon">✓</span><span>${esc(edit.path)}</span><small style="color:#9ec2ff">已应用</small></div>`;toast(`已更新 ${edit.path}`);}
      catch(err){button.disabled=false;button.textContent="应用修改";toast(err.message);}
    });
    host.append(card);
  }
}
function partialJsonString(raw,key){
  const marker=`"${key}"`;let i=raw.indexOf(marker);if(i<0)return null;
  i+=marker.length;while(i<raw.length&&/\s/.test(raw[i]))i++;if(raw[i++]!==":")return null;
  while(i<raw.length&&/\s/.test(raw[i]))i++;if(raw[i++]!=='"')return null;
  let value="";
  for(;i<raw.length;i++){
    const ch=raw[i];
    if(ch==='"')return value;
    if(ch!=="\\"){value+=ch;continue;}
    if(++i>=raw.length)break;
    const escaped=raw[i];
    const simple={"\"":"\"","\\":"\\","/":"/","b":"\b","f":"\f","n":"\n","r":"\r","t":"\t"};
    if(Object.hasOwn(simple,escaped)){value+=simple[escaped];continue;}
    if(escaped==="u"&&i+4<raw.length){const code=raw.slice(i+1,i+5);if(/^[\da-f]{4}$/i.test(code)){value+=String.fromCharCode(parseInt(code,16));i+=4;continue;}}
    value+="\\"+escaped;
  }
  return value;
}
async function streamChat(message,files,pending){
  const response=await fetch("/api/chat",{method:"POST",headers:headers(),body:JSON.stringify({message,files})});
  if(!response.ok){const data=await response.json().catch(()=>({detail:`请求失败 (${response.status})`}));throw new Error(data.detail||"模型请求失败");}
  if(!response.body)throw new Error("浏览器不支持流式响应");
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer="",raw="",result=null;
  while(true){
    const {value,done}=await reader.read();
    buffer+=decoder.decode(value||new Uint8Array(),{stream:!done}).replace(/\r\n/g,"\n");
    let boundary;
    while((boundary=buffer.indexOf("\n\n"))>=0){
      const frame=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);
      const dataLine=frame.split("\n").find(line=>line.startsWith("data: "));if(!dataLine)continue;
      const event=JSON.parse(dataLine.slice(6));
      if(event.type==="delta"){
        raw+=event.text;
        const partial=partialJsonString(raw,"message");
        if(partial!==null){pending.querySelector(".assistant-label").textContent="栈灯 · 正在生成";pending.querySelector(".assistant-message").textContent=partial;}
      }else if(event.type==="result")result=event;
      else if(event.type==="error")throw new Error(event.message||"模型请求失败");
    }
    if(done)break;
  }
  if(!result)throw new Error("响应中断，请重试");
  return result;
}
$("#chatForm").addEventListener("submit",async e=>{
  e.preventDefault();if(state.busy)return;
  const message=$("#prompt").value.trim();if(!message)return;
  state.busy=true;updateComposer();showMessage("user",message);$("#prompt").value="";resizeInput();
  const pending=showMessage("assistant","正在阅读所选文件并整理建议…");pending.querySelector(".assistant-label").textContent="栈灯 · 正在思考";
  try{
    const result=await streamChat(message,[...state.selected],pending);
    pending.querySelector(".assistant-label").textContent="栈灯 · 助手";
    pending.querySelector(".assistant-message").textContent=result.message||"已完成。";
    if(result.edits?.length)addEdits(pending,result.edits);
    else if(!result.message)pending.querySelector(".assistant-message").textContent="没有生成文件修改建议。";
  }catch(err){pending.querySelector(".assistant-label").textContent="栈灯 · 请求失败";pending.querySelector(".assistant-message").textContent=err.message;}
  finally{state.busy=false;updateComposer();$("#messages").scrollTop=$("#messages").scrollHeight;}
});
async function boot(){
  try{
    const configResponse=await fetch("/api/auth/config");const config=await configResponse.json();
    state.publicMode=Boolean(config.public_mode);
    if(state.publicMode){
      $("#localApiSettings").hidden=true;
      $("#modeEyebrow").textContent="云端工作区";
      $("#modePill").innerHTML="<i></i> 云端工作区";
      $("#chooseFolder").innerHTML="<span>＋</span> 上传项目 ZIP";
      $("#sidebarSafety").textContent="ZIP 临时隔离保存，24 小时无访问后清除";
      $("#welcome p").textContent="上传项目 ZIP 开始使用。文件按账号隔离并临时保存；只有你勾选的文件会发送给 DeepSeek。先检查 diff，确认后再应用。";
      $("#accountButton").textContent="账";$("#accountButton").title="点击退出账号";
      $("#settingsDescription").textContent="DeepSeek API Key 只保存在服务端环境变量中，不会发送到浏览器。";
      $("#settingsModel").textContent=config.model||"deepseek-flash";
      if(!config.auth_enabled){$("#authError").textContent="服务暂未完成登录配置，请稍后再试。";$("#authGate").hidden=false;return;}
      const query=new URLSearchParams(location.search),tokenHash=query.get("token_hash"),verifyType=query.get("type");
      if(tokenHash&&["signup","email"].includes(verifyType)){
        try{await api("/api/auth/verify",{method:"POST",body:JSON.stringify({token_hash:tokenHash,type:verifyType})});history.replaceState({},"",location.pathname);location.reload();return;}
        catch(err){$("#authError").textContent=err.message;$("#authGate").hidden=false;return;}
      }
      const response=await fetch("/api/me",{credentials:"same-origin"});
      if(response.status===401){$("#authGate").hidden=false;return;}
      if(!response.ok)throw new Error("暂时无法读取账号信息");
      const me=await response.json();state.authenticated=true;
      $("#accountButton").textContent=(me.email||"我").slice(0,1).toUpperCase();
      if(me.workspace)setWorkspace(me.workspace,me.files||[]);
      return;
    }
    const session=await fetch("/api/session");const data=await session.json();state.token=data.token;
    $("#settingsDescription").textContent="填写你自己的 Key。栈灯会把它保存在本机用户配置目录中，并只在调用 DeepSeek 时使用。";
    $("#settingsModel").textContent=data.model||"deepseek-flash";
    await refreshLocalSettings();
  }catch(err){toast(err.message||"无法连接服务，请稍后重试");}
}
boot();
