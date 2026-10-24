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

// Demo-only availability. A production deployment must retrieve and reserve slots atomically on the server.
const demoSlots = ["08:30","09:00","09:30","10:00","10:30","11:00","11:30","12:00"];
const demoUnavailable = {"2026-10-26":["09:00","10:30"],"2026-10-27":["08:30","09:30","11:00"],"2026-10-28":["10:00"]};
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

function refreshSlots(){
  const day=dateInput.value;
  timeSelect.innerHTML="";
  demandNote.hidden=true;
  if(!specialtySelect.value || !day){
    timeSelect.add(new Option("Elegí especialidad y fecha",""));
    note.textContent="Seleccioná especialidad y fecha para consultar los horarios de demostración.";
    return;
  }
  const date=new Date(day+"T12:00:00");
  if(date.getDay()===0){
    timeSelect.add(new Option("Sin atención los domingos",""));
    note.textContent="No hay atención cargada para el domingo. Elegí otro día.";
    return;
  }
  const taken=demoUnavailable[day]||[];
  const available=demoSlots.filter(t=>!taken.includes(t));
  if(!available.length){
    timeSelect.add(new Option("Sin horarios disponibles",""));
    note.textContent="No hay horarios disponibles para esa fecha en esta demostración.";
    return;
  }
  timeSelect.add(new Option("Seleccionar horario",""));
  available.forEach(t=>timeSelect.add(new Option(t,t)));
  note.textContent=`${available.length} horarios de ejemplo para ${specialtySelect.value}. La disponibilidad real deberá conectarse a la agenda de la clínica.`;
  if(available.length<=5){
    demandNote.hidden=false;
    demandNote.className="demand-alert";
    demandNote.textContent="Aviso de ejemplo: quedan pocos horarios de demostración. En producción, este aviso se basará en reservas reales y no en datos inventados.";
  }
}
$("#bookingForm").addEventListener("submit",e=>{
  e.preventDefault();
  if(!$("#consent").checked) return;
  const chosen=timeSelect.value;
  if(!chosen){note.textContent="Elegí un horario disponible antes de continuar.";return}
  result.hidden=false;
  result.innerHTML="<strong>Formulario de demostración completado.</strong><br>No se creó un turno real ni se enviaron correos. Para activar reservas y recordatorios hace falta conectar un backend, una base de datos y un servicio de email.";
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
const WHATSAPP_NUMBER = '5493804507584'; // WhatsApp de contacto de Pulso Digital / secretaría
const whatsappFab=document.getElementById('whatsappFab');
const whatsappChat=document.getElementById('whatsappChat');
const whatsappTeaser=document.getElementById('whatsappTeaser');
function openWhatsappChat(){whatsappChat.hidden=false;whatsappFab.setAttribute('aria-expanded','true');whatsappTeaser.classList.add('is-faded');document.getElementById('whatsappMessage').focus();}
function closeWhatsappChat(){whatsappChat.hidden=true;whatsappFab.setAttribute('aria-expanded','false');}
whatsappFab.addEventListener('click',()=>whatsappChat.hidden?openWhatsappChat():closeWhatsappChat());
document.getElementById('closeWhatsapp').addEventListener('click',closeWhatsappChat);
document.getElementById('sendWhatsapp').addEventListener('click',()=>{
  const status=document.getElementById('whatsappStatus');
  if(!/^\d{10,15}$/.test(WHATSAPP_NUMBER)){status.textContent='No se pudo validar el número de WhatsApp.';return;}
  const msg=(document.getElementById('whatsappMessage').value.trim()||'chat');
  window.open('https://wa.me/'+WHATSAPP_NUMBER+'?text='+encodeURIComponent(msg),'_blank','noopener,noreferrer');
});
// Al desplazarse, el botón se compacta; al pasar el cursor recupera su tamaño.
function updateWhatsappScrollState(){document.getElementById('whatsappWidget').classList.toggle('is-scrolled',window.scrollY>80);}
window.addEventListener('scroll',updateWhatsappScrollState,{passive:true});
updateWhatsappScrollState();
// Cualquier enlace de WhatsApp abre el chat del número configurado.
const whatsappLink=document.getElementById('whatsappLink');
if(whatsappLink){whatsappLink.href='https://wa.me/'+WHATSAPP_NUMBER;whatsappLink.addEventListener('click',e=>{e.preventDefault();window.open('https://wa.me/'+WHATSAPP_NUMBER,'_blank','noopener,noreferrer');});}

// Si se entra mediante un enlace con hash de vista interna, abrir la vista correspondiente.
const initialHash=location.hash.replace('#','');if(viewTemplates[initialHash])openInternalView(initialHash);
