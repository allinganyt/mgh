const TZ = 'Europe/Paris';
const SHEETS = {
  doctors: ['id','name','role','username','tg_id','is_active'],
  users: ['username','chat_id'],
  appointments: ['id','patient_username','patient_name','doctor_id','doctor_name','doctor_username','time_slot','complaints','appointment_at','reminded_at','created_at'],
  applications: ['id','applicant_username','name','role','experience','about']
};

function props_(){ return PropertiesService.getScriptProperties(); }
function token_(){ return props_().getProperty('BOT_TOKEN'); }
function book_(){
  const id=props_().getProperty('SPREADSHEET_ID');
  if(id) return SpreadsheetApp.openById(id);
  const ss=SpreadsheetApp.create('MGH Database');
  props_().setProperty('SPREADSHEET_ID',ss.getId());
  return ss;
}
function sheet_(name){
  const ss=book_(); let sh=ss.getSheetByName(name);
  if(!sh) sh=ss.insertSheet(name);
  if(sh.getLastRow()===0) sh.appendRow(SHEETS[name]);
  return sh;
}
function setup(){
  Object.keys(SHEETS).forEach(sheet_);
  const d=sheet_('doctors');
  if(d.getLastRow()===1){
    d.getRange(2,1,3,6).setValues([
      [1,'Д-р Маркус Вэнс','Главный хирург','mgh_vance',0,1],
      [2,'Д-р Елена Ростова','Терапевт','mgh_rostova',0,1],
      [3,'Д-р Алекс Чен','Травматолог','mgh_chen',0,1]
    ]);
  }
  ScriptApp.getProjectTriggers().filter(t=>t.getHandlerFunction()==='sendDueReminders').forEach(t=>ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('sendDueReminders').timeBased().everyMinutes(1).create();
  return 'MGH Sheets storage and reminder trigger configured';
}
function output_(data,cb){
  const json=JSON.stringify(data);
  if(cb && /^[A-Za-z_$][\w$\.]{0,80}$/.test(cb))
    return ContentService.createTextOutput(cb+'('+json+');').setMimeType(ContentService.MimeType.JAVASCRIPT);
  return ContentService.createTextOutput(json).setMimeType(ContentService.MimeType.JSON);
}
function rows_(name){
  const v=sheet_(name).getDataRange().getValues(); if(v.length<2)return [];
  const headers=v.shift(); return v.filter(r=>r.some(x=>x!=='' )).map(r=>{const o={};headers.forEach((h,i)=>o[h]=r[i]);return o;});
}
function append_(name,obj){
  const sh=sheet_(name), headers=SHEETS[name];
  sh.appendRow(headers.map(k=>obj[k]===undefined?'':obj[k]));
  return sh.getLastRow();
}
function norm_(s){return String(s||'').trim().replace(/^@+/,'').toLowerCase();}
function send_(chat,text){
  if(!token_()||!chat)return false;
  const r=UrlFetchApp.fetch('https://api.telegram.org/bot'+token_()+'/sendMessage',{
    method:'post',contentType:'application/json',payload:JSON.stringify({chat_id:chat,text:text}),
    muteHttpExceptions:true
  });
  return r.getResponseCode()===200;
}
function registerUser_(chatId,username){
  const u=norm_(username); if(!u)return;
  const sh=sheet_('users'), data=rows_('users'), idx=data.findIndex(x=>x.username===u);
  if(idx>=0)sh.getRange(idx+2,2).setValue(chatId); else sh.appendRow([u,chatId]);
}
function telegramUpdate_(update){
  const m=update.message||update.edited_message;
  if(!m||!m.chat)return;
  const username=m.from&&m.from.username||'';
  registerUser_(m.chat.id,username);
  if((m.text||'').startsWith('/start')){
    const url=props_().getProperty('MINI_APP_URL');
    const keyboard=url?{inline_keyboard:[[{text:'🏥 Открыть MGH',web_app:{url:url}}]]}:undefined;
    const payload={chat_id:m.chat.id,text:'Добро пожаловать в Miami General Hospital! Откройте приложение для записи к врачу.'};
    if(keyboard)payload.reply_markup=keyboard;
    UrlFetchApp.fetch('https://api.telegram.org/bot'+token_()+'/sendMessage',{method:'post',contentType:'application/json',payload:JSON.stringify(payload),muteHttpExceptions:true});
  }
}
function doPost(e){
  try{
    const raw=e&&e.postData&&e.postData.contents||'{}';
    const data=JSON.parse(raw);
    if(data.update_id!==undefined){telegramUpdate_(data);return output_({ok:true});}
    return output_({ok:false,error:'Unsupported POST'});
  }catch(err){return output_({ok:false,error:String(err)});}
}
function doGet(e){
  const p=e.parameter||{}, action=p.action||'health', cb=p.callback;
  try{
    if(action==='health')return output_({ok:true,service:'MGH Apps Script'});
    if(action==='state'){
      const doctors=rows_('doctors').map(d=>({id:Number(d.id),name:d.name,role:d.role,username:d.username,tg_id:Number(d.tg_id)||0,is_active:Number(d.is_active)}));
      return output_({doctors:doctors,applications:rows_('applications'),appointments:rows_('appointments').slice(-30).reverse(),cooldown_left:0},cb);
    }
    const body=p.data?JSON.parse(p.data):{};
    if(action==='appointment'){
      const u=norm_(body.patient_username), docs=rows_('doctors'), d=docs.find(x=>Number(x.id)===Number(body.doctor_id)&&Number(x.is_active)===1);
      if(!u||!d)throw new Error(!u?'Укажите @username Telegram':'Врач недоступен');
      const match=String(body.time_slot||'').match(/^(Сегодня|Завтра),\s*(\d{1,2}):(\d{2})$/);
      if(!match)throw new Error('Некорректное время приёма');
      const day=new Date(); if(match[1]==='Завтра')day.setDate(day.getDate()+1);
      day.setHours(Number(match[2]),Number(match[3]),0,0);
      if(day.getTime()<=Date.now())throw new Error('Это время уже прошло');
      const stamp=Utilities.formatDate(day,'Europe/Paris',"yyyy-MM-dd'T'HH:mm:ssXXX");
      const id=append_('appointments',{id:sheet_('appointments').getLastRow(),patient_username:u,patient_name:body.patient_name||('@'+u),doctor_id:Number(d.id),doctor_name:d.name,doctor_username:norm_(d.username),time_slot:body.time_slot,complaints:body.complaints||'Плановый осмотр',appointment_at:stamp,reminded_at:'',created_at:new Date()});
      const users=rows_('users'), pu=users.find(x=>x.username===u), du=users.find(x=>x.username===norm_(d.username));
      if(pu)send_(pu.chat_id,'🏥 MGH — вы записаны на приём!\nВрач: '+d.name+'\nВремя: '+body.time_slot+'\nПричина: '+(body.complaints||'Плановый осмотр'));
      if(du)send_(du.chat_id,'🩺 MGH — новая запись\nПациент: '+(body.patient_name||u)+' (@'+u+')\nВремя: '+body.time_slot+'\nЖалобы: '+(body.complaints||'Не указано'));
      return output_({ok:true,id:id},cb);
    }
    if(action==='application'){
      const u=norm_(body.applicant_username);if(!u||!body.name||!body.role)throw new Error('Заполните username, имя и должность');
      append_('applications',{id:sheet_('applications').getLastRow(),applicant_username:u,name:body.name,role:body.role,experience:body.experience||'',about:body.about||''});
      return output_({ok:true},cb);
    }
    if(action.startsWith('admin_')){
      if(body.pin!==props_().getProperty('ADMIN_PIN'))throw new Error('Неверный код администратора');
      if(action==='admin_add'){
        const u=norm_(body.username);append_('doctors',{id:sheet_('doctors').getLastRow(),name:body.name,role:body.role,username:u,tg_id:0,is_active:1});
      } else if(action==='admin_toggle'){
        const sh=sheet_('doctors'), ds=rows_('doctors'),i=ds.findIndex(x=>Number(x.id)===Number(body.doctor_id));if(i<0)throw new Error('Врач не найден');
        sh.getRange(i+2,6).setValue(Number(ds[i].is_active)===1?0:1);
      } else if(action==='admin_review'){
        const sh=sheet_('applications'), apps=rows_('applications'),i=apps.findIndex(x=>Number(x.id)===Number(body.app_id));if(i<0)throw new Error('Анкета не найдена');
        const a=apps[i];if(body.approve){const user=rows_('users').find(x=>x.username===a.applicant_username);append_('doctors',{id:sheet_('doctors').getLastRow(),name:a.name,role:a.role,username:a.applicant_username,tg_id:user?user.chat_id:0,is_active:1});if(user)send_(user.chat_id,'🎉 Ваша анкета MGH одобрена! Должность: '+a.role);}
        sh.deleteRow(i+2);
      }
      return output_({ok:true},cb);
    }
    throw new Error('Unknown action: '+action);
  }catch(err){return output_({ok:false,detail:String(err.message||err)},cb);}
}
function sendDueReminders(){
  const sh=sheet_('appointments'), data=rows_('appointments'), users=rows_('users'), now=Date.now();
  data.forEach((a,i)=>{
    if(!a.appointment_at||a.reminded_at)return;
    const due=new Date(a.appointment_at).getTime();if(!due||due>now)return;
    const user=users.find(u=>u.username===a.patient_username);if(!user)return;
    if(send_(user.chat_id,'⏰ MGH — время вашего приёма!\nВрач: '+a.doctor_name+'\nВремя: '+a.time_slot+'\nПожалуйста, не опаздывайте.')){
      sh.getRange(i+2,10).setValue(new Date());
    }
  });
}
function configureTelegram(){
  const url=props_().getProperty('WEB_APP_URL');
  if(!url||!token_())throw new Error('Set WEB_APP_URL and BOT_TOKEN in Script Properties first');
  const r=UrlFetchApp.fetch('https://api.telegram.org/bot'+token_()+'/setWebhook',{method:'post',payload:{url:url},muteHttpExceptions:true});
  Logger.log(r.getContentText());
}
