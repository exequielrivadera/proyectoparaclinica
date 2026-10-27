const API_BASE = (window.CLINICA_API_BASE !== undefined ? window.CLINICA_API_BASE : ((location.hostname === '127.0.0.1' || location.hostname === 'localhost') ? 'http://127.0.0.1:5000' : '')).replace(/\/$/, '');
async function apiRequest(path, options={}) {
  if (location.hostname.endsWith('github.io') && !API_BASE) {
    throw new Error('La API todavía no está conectada. Publicá el backend Flask en Render y configurá su URL HTTPS en js/config.js.');
  }
  let response;
  try { response = await fetch(API_BASE + path, {
    ...options,
    headers: {'Content-Type':'application/json', ...(options.headers||{})}
  }); } catch (error) {
    if (error instanceof TypeError) throw new Error('No se pudo conectar con el backend. Verificá la URL HTTPS de la API y la configuración CORS.');
    throw error;
  }
  const data = await response.json().catch(()=>({error:'El backend devolvió una respuesta que no es JSON. Revisá la URL y los registros del servidor.'}));
  if (!response.ok) throw new Error(data.error || 'No se pudo completar la solicitud.');
  return data;
}
const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const bookingDialog = $("#bookingDialog");
const portalDialog = $("#portalDialog");
const dateInput = $("#appointmentDate");
const timeSelect = $("#timeSelect");
const specialtySelect = $("#specialtySelect");
const doctorSelect = $("#doctorSelect");
const note = $("#availabilityNote");
const demandNote = $("#demandNote");
const result = $("#bookingResult");
$("#year").textContent = new Date().getFullYear();

// La disponibilidad se consulta en el backend para que reservas y horarios compartan la misma agenda.
function localDate(d){ const x=new Date(d); x.setMinutes(x.getMinutes()-x.getTimezoneOffset()); return x.toISOString().slice(0,10); }
dateInput.min = localDate(new Date());
dateInput.value = localDate(new Date(Date.now()+86400000));
function showBooking({specialty="",doctor=""}={}) {
  if(specialty) specialtySelect.value=specialty;
  if(doctor) doctorSelect.value=doctor;
  result.hidden=true;
  bookingDialog.showModal();
  refreshSlots();
}
$$("[data-open-booking]").forEach(b=>b.addEventListener("click",()=>showBooking()));
$$("[data-specialty]").forEach(b=>b.addEventListener("click",()=>showBooking({specialty:b.dataset.specialty})));
$$("[data-doctor]").forEach(b=>b.addEventListener("click",()=>showBooking({doctor:b.dataset.doctor})));
$("#openPortal").addEventListener("click",()=>portalDialog.showModal());
$$("[data-close]").forEach(b=>b.addEventListener("click",()=>$("#"+b.dataset.close).close()));
$("#navToggle").addEventListener("click",()=>{const nav=$("#mainNav");nav.classList.toggle("open");$("#navToggle").setAttribute("aria-expanded",nav.classList.contains("open")?"true":"false")});
$$('#mainNav a').forEach(a=>a.addEventListener("click",()=>$("#mainNav").classList.remove("open")));
dateInput.addEventListener("change",refreshSlots);
specialtySelect.addEventListener("change",refreshSlots);
doctorSelect.addEventListener("change",refreshSlots);

function getChosenDoctor(){
  const mapping={
    "Cardiología":"Dra. Ana López",
    "Clínica Médica":"Dr. Martín Pérez",
    "Pediatría":"Dra. Sofía Gómez"
  };
  const selected=doctorSelect.value;
  const valid={
    "Cardiología":["Dra. Ana López"],
    "Clínica Médica":["Dr. Martín Pérez"],
    "Pediatría":["Dra. Sofía Gómez"],
    "Dermatología":["Profesional a incorporar"],
    "Ginecología":["Profesional a incorporar"],
    "Traumatología":["Profesional a incorporar"]
  };
  return (valid[specialtySelect.value]||[]).includes(selected)
    ? selected : (mapping[specialtySelect.value] || "Profesional a incorporar");
}
async function refreshSlots(){
  const day=dateInput.value;
  timeSelect.innerHTML="";
  demandNote.hidden=true;
  if(!specialtySelect.value || !day){
    timeSelect.add(new Option("Elegí especialidad y fecha",""));
    note.textContent="Seleccioná especialidad y fecha para consultar los horarios.";
    return;
  }
  const specialty=specialtySelect.value;
  const chosenDoctor=getChosenDoctor();
  timeSelect.add(new Option("Consultando horarios…",""));
  note.textContent="Consultando disponibilidad de la agenda…";
  try{
    const params=new URLSearchParams({specialty,date:day,doctor:chosenDoctor});
    const data=await apiRequest('/api/availability?'+params.toString());
    timeSelect.innerHTML="";
    if(!data.slots || !data.slots.length){
      timeSelect.add(new Option("Sin horarios disponibles",""));
      note.textContent=data.message || "No hay horarios disponibles para esa fecha.";
      return;
    }
    timeSelect.add(new Option("Seleccionar horario",""));
    data.slots.forEach(t=>timeSelect.add(new Option(t,t)));
    note.textContent=`${data.slots.length} horarios ${data.demo?'de demostración':'disponibles'} para ${specialty}.`;
    if(data.slots.length<=3){
      demandNote.hidden=false; demandNote.className="demand-alert";
      demandNote.textContent=data.demo
        ?"Quedan pocos horarios en esta agenda de demostración."
        :"Quedan pocos horarios disponibles para esta fecha.";
    }
  }catch(error){
    timeSelect.innerHTML="";
    timeSelect.add(new Option("Agenda no disponible",""));
    note.textContent=`No pudimos consultar la agenda: ${error.message || "error de conexión"}. Revisá la terminal del backend.`;
  }
}
$("#bookingForm").addEventListener("submit",async e=>{
  e.preventDefault();
  if(!$("#consent").checked) return;
  const chosen=timeSelect.value;
  if(!chosen){note.textContent="Elegí un horario disponible antes de continuar.";return}
  const specialty=specialtySelect.value;
  const doctor=getChosenDoctor();
  const submitButton=$("#bookingForm button[type='submit']");
  submitButton.disabled=true; submitButton.textContent="Guardando turno…";
  result.hidden=false;
  result.textContent="Registrando la solicitud…";
  try{
    const data=await apiRequest('/api/appointments',{method:'POST',body:JSON.stringify({
      first_names:$("#firstNames").value.trim(),
      last_names:$("#lastNames").value.trim(),
      dni:$("#dni").value.trim(),
      sex:$("#sex").value,
      email:$("#email").value.trim(),
      phone:$("#phone").value.trim(),
      specialty,doctor,date:dateInput.value,time:chosen,consent:$("#consent").checked
    })});
    result.textContent="";
    const strong=document.createElement('strong');
    strong.textContent=data.demo?'Turno de demostración registrado.':'¡Tu turno está registrado!';
    result.appendChild(strong);
    const detail=document.createElement('p');
    detail.textContent=`${data.appointment.doctor} · ${data.appointment.specialty} · ${data.appointment.date} a las ${data.appointment.time}.`;
    result.appendChild(detail);
    const email=document.createElement('p');
    email.textContent=data.email_sent?'Enviamos la confirmación a tu correo.':'El turno quedó guardado, pero el correo no se envió. La clínica debe configurar el servicio de correo.';
    result.appendChild(email);
    if(data.demo){
      const demo=document.createElement('p'); demo.textContent='Esta es una agenda de prueba. No uses datos reales de pacientes.'; result.appendChild(demo);
    }
    await refreshSlots();
  }catch(error){
    result.textContent=error.message;
    if(error.message.includes('ocup')) await refreshSlots();
  }finally{
    submitButton.disabled=false; submitButton.textContent="Solicitar turno";
  }
  result.scrollIntoView({block:"nearest",behavior:"smooth"});
});
$("#portalForm").addEventListener("submit",e=>{
  e.preventDefault();
  const r=$("#portalResult");
  r.hidden=false;
  r.textContent="El portal está desactivado en esta demo. No se verificaron credenciales ni se accedió a información médica.";
});
$("#whatsappLink").addEventListener("click",e=>{ e.preventDefault(); openWhatsappChat(); });
if("serviceWorker" in navigator && location.protocol.startsWith("http")){
  window.addEventListener("load",()=>navigator.serviceWorker.register("./service-worker.js").catch(()=>{}));
}


// Vistas internas: se cambia el contenido sin abandonar la página ni recargarla.
const internalView = document.getElementById("internalView");
const internalViewContent = document.getElementById("internalViewContent");
const viewTemplates = {
  profesionales: `
    <div class="internal-hero"><span class="eyebrow">NUESTRO EQUIPO</span><h1>Profesionales para acompañarte.</h1><p>Conocé al equipo por especialidad y elegí con quién querés atenderte. Los perfiles de esta demo son ilustrativos.</p></div>
    <div class="internal-filter" role="group" aria-label="Filtrar profesionales"><button class="filter-chip active" data-prof-filter="Todos">Todos</button><button class="filter-chip" data-prof-filter="Pediatría">Pediatría</button><button class="filter-chip" data-prof-filter="Clínica Médica">Clínica Médica</button><button class="filter-chip" data-prof-filter="Cardiología">Cardiología</button><button class="filter-chip" data-prof-filter="Dermatología">Dermatología</button><button class="filter-chip" data-prof-filter="Ginecología">Ginecología</button><button class="filter-chip" data-prof-filter="Traumatología">Traumatología</button></div>
    <div class="professional-groups">
      <section class="professional-group" data-prof-category="Pediatría"><div class="group-heading"><h2>Pediatría</h2><p>Salud y desarrollo infantil.</p></div><div class="professional-cards"><article class="professional-card"><div class="doctor-avatar avatar-c">SG</div><div><span class="doctor-specialty">PEDIATRÍA</span><h3>Dra. Sofía Gómez</h3><p>Atención pediátrica y acompañamiento familiar.</p><button class="btn btn-small" data-book-doctor="Dra. Sofía Gómez" data-book-specialty="Pediatría">Solicitar turno</button></div></article></div></section>
      <section class="professional-group" data-prof-category="Clínica Médica"><div class="group-heading"><h2>Clínica Médica</h2><p>Consultas generales, prevención y seguimiento.</p></div><div class="professional-cards"><article class="professional-card"><div class="doctor-avatar avatar-b">MP</div><div><span class="doctor-specialty">CLÍNICA MÉDICA</span><h3>Dr. Martín Pérez</h3><p>Medicina general y seguimiento clínico.</p><button class="btn btn-small" data-book-doctor="Dr. Martín Pérez" data-book-specialty="Clínica Médica">Solicitar turno</button></div></article></div></section>
      <section class="professional-group" data-prof-category="Cardiología"><div class="group-heading"><h2>Cardiología</h2><p>Prevención y cuidado cardiovascular.</p></div><div class="professional-cards"><article class="professional-card"><div class="doctor-avatar avatar-a">AL</div><div><span class="doctor-specialty">CARDIOLOGÍA</span><h3>Dra. Ana López</h3><p>Atención cardiovascular y prevención.</p><button class="btn btn-small" data-book-doctor="Dra. Ana López" data-book-specialty="Cardiología">Solicitar turno</button></div></article></div></section>
      <section class="professional-group" data-prof-category="Dermatología"><div class="group-heading"><h2>Dermatología</h2><p>Consulta y cuidado integral de la piel.</p></div><div class="professional-cards"><article class="professional-card placeholder-prof"><div class="doctor-avatar avatar-d">DE</div><div><span class="doctor-specialty">DERMATOLOGÍA</span><h3>Profesional a incorporar</h3><p>Espacio preparado para agregar profesionales y sus agendas.</p><button class="btn btn-outline btn-small" data-book-specialty="Dermatología">Consultar turnos</button></div></article></div></section>
      <section class="professional-group" data-prof-category="Ginecología"><div class="group-heading"><h2>Ginecología</h2><p>Salud, prevención y acompañamiento.</p></div><div class="professional-cards"><article class="professional-card placeholder-prof"><div class="doctor-avatar avatar-e">GI</div><div><span class="doctor-specialty">GINECOLOGÍA</span><h3>Profesional a incorporar</h3><p>Espacio preparado para agregar profesionales y sus agendas.</p><button class="btn btn-outline btn-small" data-book-specialty="Ginecología">Consultar turnos</button></div></article></div></section>
      <section class="professional-group" data-prof-category="Traumatología"><div class="group-heading"><h2>Traumatología</h2><p>Huesos, articulaciones y movimiento.</p></div><div class="professional-cards"><article class="professional-card placeholder-prof"><div class="doctor-avatar avatar-f">TR</div><div><span class="doctor-specialty">TRAUMATOLOGÍA</span><h3>Profesional a incorporar</h3><p>Espacio preparado para agregar profesionales y sus agendas.</p><button class="btn btn-outline btn-small" data-book-specialty="Traumatología">Consultar turnos</button></div></article></div></section>
    </div><p class="demo-note">Los nombres y perfiles son ficticios. Las especialidades sin profesional asignado están preparadas para completar con datos reales.</p>`,
  clinica: `<div class="internal-hero clinic-history-hero"><span class="eyebrow">NUESTRA HISTORIA</span><h1>Una clínica que crece con su comunidad.</h1><p>Creemos que una buena atención combina conocimiento médico, escucha y organización. Por eso buscamos que cada persona encuentre un espacio de confianza desde el primer contacto.</p></div><div class="history-layout"><div class="history-art"><div class="history-plus">+</div><span>ATENCIÓN<br>CON CALIDEZ</span></div><div class="history-copy"><span class="eyebrow">QUIÉNES SOMOS</span><h2>La salud empieza con una conversación.</h2><p>Clínica Demo es una identidad de muestra creada para presentar una experiencia digital adaptable a consultorios y centros médicos. En la versión final, este espacio contará la historia real de la institución, su equipo, sus valores y los servicios que brinda.</p><p>Queremos que pedir un turno sea sencillo, que la información esté clara y que cada paciente pueda recibir acompañamiento antes y después de la consulta.</p><div class="values-grid"><div><strong>01</strong><h3>Cercanía</h3><p>Escucha y atención respetuosa.</p></div><div><strong>02</strong><h3>Confianza</h3><p>Información clara y responsable.</p></div><div><strong>03</strong><h3>Organización</h3><p>Turnos y documentación más accesibles.</p></div></div><button class="btn" data-open-booking>Solicitar un turno</button></div></div><div class="history-contact"><div><span class="eyebrow">ESTAMOS PARA VOS</span><h2>¿Querés conocernos mejor?</h2><p>Escribinos o solicitá un turno para recibir orientación.</p></div><button class="btn btn-outline" data-open-whatsapp>Contactar a secretaría</button></div>`,
  especialidades: `<div class="internal-hero"><span class="eyebrow">ESPECIALIDADES</span><h1>Atención para cada etapa de tu vida.</h1><p>Explorá los rubros médicos y avanzá a la solicitud de turno con la especialidad que necesitás.</p></div><div class="specialty-grid internal-specialty-grid"><button class="specialty" data-specialty="Clínica Médica"><span class="specialty-icon mint">✚</span><strong>Clínica Médica</strong><small>Atención general y seguimiento</small></button><button class="specialty" data-specialty="Cardiología"><span class="specialty-icon peach">♡</span><strong>Cardiología</strong><small>Cuidado de la salud cardiovascular</small></button><button class="specialty" data-specialty="Pediatría"><span class="specialty-icon blue">☼</span><strong>Pediatría</strong><small>Salud y desarrollo infantil</small></button><button class="specialty" data-specialty="Dermatología"><span class="specialty-icon lavender">◉</span><strong>Dermatología</strong><small>Cuidado integral de la piel</small></button><button class="specialty" data-specialty="Ginecología"><span class="specialty-icon peach">✿</span><strong>Ginecología</strong><small>Salud y prevención</small></button><button class="specialty" data-specialty="Traumatología"><span class="specialty-icon mint">⌁</span><strong>Traumatología</strong><small>Huesos, articulaciones y movimiento</small></button></div><div class="specialty-cta"><div><h2>¿No sabés qué especialidad elegir?</h2><p>Contactá a secretaría y te orientamos.</p></div><button class="btn" data-open-whatsapp>Te asesoramos</button></div>`
};
function openInternalView(name){
  if(!viewTemplates[name]) return;
  internalViewContent.innerHTML=viewTemplates[name];
  internalView.classList.add('is-open');internalView.removeAttribute('inert');internalView.setAttribute('aria-hidden','false');
  document.body.classList.add('internal-view-active');internalView.scrollTop=0;internalViewContent.scrollTop=0;
  history.replaceState(null,'','#'+name);
  bindInternalView();
  const nav=document.getElementById('mainNav');nav.classList.remove('open');
}
function closeInternalView(){internalView.classList.remove('is-open');internalView.setAttribute('inert','');internalView.setAttribute('aria-hidden','true');document.body.classList.remove('internal-view-active');history.replaceState(null,'',location.pathname+location.search);}
document.querySelectorAll('[data-view-link]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault();openInternalView(el.dataset.viewLink)}));
document.getElementById('viewBack').addEventListener('click',closeInternalView);
function bindInternalView(){
  internalViewContent.querySelectorAll('[data-prof-filter]').forEach(btn=>btn.addEventListener('click',()=>{internalViewContent.querySelectorAll('[data-prof-filter]').forEach(b=>b.classList.toggle('active',b===btn));internalViewContent.querySelectorAll('[data-prof-category]').forEach(group=>group.hidden=btn.dataset.profFilter!=='Todos'&&group.dataset.profCategory!==btn.dataset.profFilter)}));
  internalViewContent.querySelectorAll('[data-specialty]').forEach(btn=>btn.addEventListener('click',()=>showBooking({specialty:btn.dataset.specialty})));
  internalViewContent.querySelectorAll('[data-book-doctor]').forEach(btn=>btn.addEventListener('click',()=>showBooking({doctor:btn.dataset.bookDoctor,specialty:btn.dataset.bookSpecialty})));
  internalViewContent.querySelectorAll('[data-book-specialty]').forEach(btn=>btn.addEventListener('click',()=>showBooking({specialty:btn.dataset.bookSpecialty})));
  internalViewContent.querySelectorAll('[data-open-booking]').forEach(btn=>btn.addEventListener('click',()=>showBooking()));
  internalViewContent.querySelectorAll('[data-open-whatsapp]').forEach(btn=>btn.addEventListener('click',openWhatsappChat));
}

// WhatsApp flotante persistente. Configurar el número real en formato internacional sin + ni espacios.
const WHATSAPP_NUMBER = '5493804507584'; // WhatsApp indicado por el responsable del proyecto.
const whatsappFab=document.getElementById('whatsappFab');
const whatsappChat=document.getElementById('whatsappChat');
const whatsappTeaser=document.getElementById('whatsappTeaser');
function openWhatsappChat(){whatsappChat.hidden=false;whatsappFab.setAttribute('aria-expanded','true');whatsappTeaser.classList.add('is-faded');document.getElementById('whatsappMessage').focus();}
const DEFAULT_WHATSAPP_MESSAGE='Hola, necesito asesoramiento, por favor.';
function sendWhatsappMessage(message){
  if(!/^5493804507584$/.test(WHATSAPP_NUMBER)){
    document.getElementById('whatsappStatus').textContent='No se pudo validar el número de WhatsApp.';
    return;
  }
  window.open('https://wa.me/'+WHATSAPP_NUMBER+'?text='+encodeURIComponent(message),'_blank','noopener,noreferrer');
}
function closeWhatsappChat(){whatsappChat.hidden=true;whatsappFab.setAttribute('aria-expanded','false');}
whatsappFab.addEventListener('click',()=>whatsappChat.hidden?openWhatsappChat():closeWhatsappChat());
document.getElementById('closeWhatsapp').addEventListener('click',closeWhatsappChat);

const chatMessages=document.getElementById('chatMessages');
const chatOptions=document.getElementById('chatQuickOptions');
const chatQuickTitle=document.getElementById('chatQuickTitle');
const chatInput=document.getElementById('chatInput');
const chatInputForm=document.getElementById('chatInputForm');
const chatStatus=document.getElementById('whatsappStatus');
const chatResetHome=document.getElementById('chatResetHome');
let botState='menu';
function addChatMessage(text,who='bot'){
  const bubble=document.createElement('div');
  bubble.className='chat-bubble '+(who==='user'?'user-message':'bot-message');
  bubble.textContent=text;
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop=chatMessages.scrollHeight;
}
function setBotPrompt(prompt,placeholder='Escribí tu respuesta...'){
  chatInput.placeholder=placeholder;
  chatInput.setAttribute('aria-label',placeholder);
  chatQuickTitle.textContent=prompt||'';
  chatOptions.hidden=!prompt;
}
function showCleanAnswer(answer){
  chatMessages.replaceChildren();
  addChatMessage(answer,'bot');
  chatOptions.hidden=true;
  chatQuickTitle.textContent='';
  chatInputForm.hidden=true;
  chatResetHome.hidden=false;
  chatStatus.textContent='Consulta finalizada. Volvé al inicio para realizar otra consulta.';
  botState='answered';
}
function returnToBotHome(){
  chatMessages.replaceChildren();
  addChatMessage('¡Hola! 👋 Soy el asistente virtual de la clínica. ¿En qué podemos ayudarte?','bot');
  chatResetHome.hidden=true;
  chatInputForm.hidden=false;
  chatInput.value='';
  botState='menu';
  setBotPrompt('Elegí una opción:');
  chatOptions.hidden=false;
  chatStatus.textContent='Asistente demostrativo: la agenda y los datos de ejemplo no son reales.';
}
chatResetHome.addEventListener('click',returnToBotHome);
function chooseBotAction(action){
  if(action==='appointment'){
    botState='dni'; addChatMessage('Para buscar tu turno, ingresá tu DNI sin puntos ni espacios. En esta demo usá 30123456.','bot');
    setBotPrompt('Consulta de turno','Ingresá tu DNI'); chatOptions.hidden=true; chatInput.focus(); return;
  }
  if(action==='specialties'){
    showCleanAnswer('Estas son las especialidades de ejemplo: Clínica Médica, Cardiología y Pediatría. También están previstas Dermatología, Ginecología y Traumatología. Los profesionales y servicios deben confirmarse con la clínica antes de publicar la web.'); return;
  }
  if(action==='hours'){
    showCleanAnswer('Los horarios y la dirección todavía deben configurarse con los datos reales de la clínica. En esta demo no quiero darte información que podría ser incorrecta.'); return;
  }
  if(action==='preparation'){
    addChatMessage('La preparación depende del estudio o consulta. Decime cuál necesitás consultar; la información deberá ser validada por el equipo médico. No suspendas medicamentos ni cambies indicaciones sin consultar a un profesional.','bot');
    botState='preparation'; setBotPrompt('¿Para qué consulta o estudio?','Ej.: análisis de sangre'); chatOptions.hidden=true; chatInput.focus();
  }
}
chatOptions.querySelectorAll('[data-bot-action]').forEach(btn=>btn.addEventListener('click',()=>chooseBotAction(btn.dataset.botAction)));
document.getElementById('humanWhatsapp').addEventListener('click',()=>{
  sendWhatsappMessage('Hola, necesito asesoramiento y quisiera hablar con una persona de la clínica, por favor.');
});
chatInputForm.addEventListener('submit',event=>{
  event.preventDefault();
  const value=chatInput.value.trim(); if(!value)return;
  addChatMessage(value,'user'); chatInput.value='';
  if(botState==='dni'){
    const dni=value.replace(/\D/g,'');
    if(!/^\d{7,9}$/.test(dni)){
      addChatMessage('El DNI no parece válido. Ingresá entre 7 y 9 números, sin puntos.','bot'); return;
    }
    chatInput.disabled=true;
    apiRequest('/api/bot/appointment-lookup',{method:'POST',body:JSON.stringify({dni})})
      .then(data=>{
        if(data.found && data.appointments.length){
          const details=data.appointments.map(a=>`${a.doctor} · ${a.specialty} · ${a.date} a las ${a.time}`).join('\\n');
          showCleanAnswer(`Encontré tu turno${data.appointments.length>1?'s':''}:\\n${details}${data.demo?'\\n\\nTurno ficticio de demostración.':''}`);
        }else{
          showCleanAnswer(data.message || 'No encontré turnos para ese DNI en la agenda de demostración.');
        }
      })
      .catch(error=>showCleanAnswer(error.message))
      .finally(()=>{chatInput.disabled=false;});
    return;
  }
  if(botState==='preparation'){
    showCleanAnswer('Gracias. En la versión final esta respuesta se basará en indicaciones aprobadas por la clínica. Por ahora, confirmá la preparación directamente con el equipo médico.'); return;
  }
  const normalized=value.toLowerCase();
  if(/turno|cita|reserva/.test(normalized)){chooseBotAction('appointment');return;}
  if(/especialidad|médico|medico|profesional/.test(normalized)){chooseBotAction('specialties');return;}
  if(/horario|dirección|direccion|ubicación|ubicacion/.test(normalized)){chooseBotAction('hours');return;}
  addChatMessage('Puedo ayudarte con consultas de turnos, especialidades, horarios o preparación general. Elegí una opción para continuar.','bot');
  setBotPrompt('Elegí una opción:'); chatOptions.hidden=false;
});
// Al desplazarse, el widget se compacta; el texto desaparece en degradado. Hover/foco recupera tamaño.
function updateWhatsappCompact(){document.getElementById('whatsappWidget').classList.toggle('is-compact',window.scrollY>35);}
window.addEventListener('scroll',updateWhatsappCompact,{passive:true});
updateWhatsappCompact();
const whatsappLink=document.getElementById('whatsappLink');
const whatsappHref='https://wa.me/'+WHATSAPP_NUMBER;
whatsappLink.href=whatsappHref;
whatsappLink.target='_blank';
whatsappLink.rel='noopener noreferrer';
whatsappLink.querySelector('small').textContent='+54 9 380 450-7584';
whatsappLink.addEventListener('click',e=>{e.preventDefault();window.open(whatsappHref,'_blank','noopener,noreferrer');});
// Si se entra mediante un enlace con hash de vista interna, abrir la vista correspondiente.
const initialHash=location.hash.replace('#','');if(viewTemplates[initialHash])openInternalView(initialHash);
