# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani — Cloudtart (https://cloudtart.com)
# Additional terms under GPLv3 section 7(b): the author attribution shown in
# this user interface must be kept (see NOTICE.md).
"""The user interface: one self-contained page, English and Persian."""
from __future__ import annotations

import json

from . import ABOUT

ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
        "%3Crect width='64' height='64' rx='14' fill='%230f766e'/%3E"
        "%3Crect x='11' y='13' width='42' height='6' rx='2.5' fill='%23fff'/%3E"
        "%3Crect x='29' y='19' width='6' height='9' fill='%23fff'/%3E"
        "%3Cpath d='M18 27h28l5 24H13z' fill='%23fff'/%3E"
        "%3Crect x='23' y='34' width='18' height='8' rx='2' fill='%2308403c'/%3E"
        "%3Crect x='26' y='37' width='12' height='2' rx='1' fill='%23fff'/%3E%3C/svg%3E")

_STYLE = r"""
:root{--bg:#f4f6f8;--card:#fff;--ink:#16202a;--muted:#5b6b7a;--line:#dde3e9;--brand:#0f766e;
--brand-ink:#fff;--soft:#e6f4f2;--ok:#15803d;--warn:#b45309;--bad:#b91c1c;--mono:Consolas,"Cascadia Mono",monospace;
--shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.08)}
@media (prefers-color-scheme:dark){:root{--bg:#0e1419;--card:#161e25;--ink:#e6edf3;--muted:#93a4b3;
--line:#26323d;--brand:#2dd4bf;--brand-ink:#062b27;--soft:#12302d;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171;
--shadow:none}}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.55 "Segoe UI",Tahoma,system-ui,-apple-system,sans-serif}
a{color:var(--brand)}
header{background:var(--card);border-bottom:1px solid var(--line)}
.bar{max-width:1080px;margin:0 auto;padding:12px 16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.logo{width:36px;height:36px;border-radius:9px}
.title{font-weight:700;font-size:17px}
.sub{color:var(--muted);font-size:12.5px}
.spacer{flex:1}
.pill{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;
padding:2px 10px;font-size:12px;color:var(--muted);background:var(--card);white-space:nowrap}
.pill.brand{border-color:var(--brand);color:var(--brand)}
nav{max-width:1080px;margin:0 auto;padding:0 16px;display:flex;gap:4px;overflow-x:auto}
nav button{border:0;background:none;color:var(--muted);padding:10px 12px;font:inherit;cursor:pointer;
border-bottom:2px solid transparent;white-space:nowrap}
nav button.on{color:var(--brand);border-bottom-color:var(--brand);font-weight:600}
main{max-width:1080px;margin:0 auto;padding:18px 16px 32px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:14px;
box-shadow:var(--shadow)}
h2{font-size:16px;margin:0 0 4px}
h3{font-size:14px;margin:14px 0 6px}
p{margin:6px 0}
.muted{color:var(--muted)}
.small{font-size:12.5px}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.btn{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:7px 14px;
font:inherit;cursor:pointer}
.btn:hover{border-color:var(--brand)}
.btn.primary{background:var(--brand);border-color:var(--brand);color:var(--brand-ink);font-weight:600}
.btn.danger{color:var(--bad)}
.btn:disabled{opacity:.55;cursor:default}
input,select{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:6px 9px;min-width:0}
input:focus,select:focus{outline:2px solid var(--soft);border-color:var(--brand)}
label.f{display:flex;flex-direction:column;gap:3px;font-size:12.5px;color:var(--muted)}
.mono,.ltr{direction:ltr;unicode-bidi:isolate}
.mono{font-family:var(--mono);font-size:12.5px}
.weight{font:600 44px/1.1 var(--mono);direction:ltr;text-align:center;margin:8px 0 2px;letter-spacing:.5px}
.weight small{font-size:18px;color:var(--muted);margin-inline-start:6px}
.state{display:flex;justify-content:center;gap:8px;align-items:center;font-size:12.5px;color:var(--muted)}
.dot{width:10px;height:10px;border-radius:50%;background:var(--line);display:inline-block}
.dot.ok{background:var(--ok)}.dot.warn{background:var(--warn)}.dot.bad{background:var(--bad)}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:4px 12px;font-size:13px}
.kv b{font-weight:600;color:var(--muted)}
.progress{height:8px;background:var(--line);border-radius:99px;overflow:hidden}
.progress>div{height:100%;background:var(--brand);width:0;transition:width .3s}
.log{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;max-height:240px;
overflow:auto;font-size:12.5px}
.log div{padding:1px 0;border-bottom:1px dashed var(--line)}
.log .found{color:var(--ok);font-weight:600}.log .bad{color:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:start;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px}
.tag{display:inline-block;padding:0 8px;border-radius:99px;font-size:11.5px;background:var(--soft);color:var(--brand)}
.tag.warn{background:rgba(180,83,9,.12);color:var(--warn)}
.note{border-inline-start:3px solid var(--brand);background:var(--soft);padding:8px 12px;border-radius:6px;margin:8px 0}
.note.warn{border-color:var(--warn);background:rgba(180,83,9,.08)}
.steps{margin:0;padding-inline-start:20px}.steps li{margin:6px 0}
.empty{text-align:center;padding:28px 12px;color:var(--muted)}
.hidden{display:none!important}
.check{display:flex;gap:8px;align-items:flex-start;padding:6px 0;border-bottom:1px solid var(--line)}
.check:last-child{border-bottom:0}
.wrap{overflow-wrap:anywhere}
footer{border-top:1px solid var(--line);background:var(--card)}
footer .bar{font-size:12.5px;color:var(--muted);justify-content:center;text-align:center}
footer a{text-decoration:none}
h3 .num{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;background:var(--soft);
color:var(--brand);font-size:12px;margin-inline-end:8px;vertical-align:1px}
html[dir=rtl] .kv>.mono,html[dir=rtl] .kv>.ltr{text-align:right}
.toast{position:fixed;inset-inline:0;bottom:18px;display:flex;justify-content:center;pointer-events:none}
.toast div{background:var(--ink);color:var(--bg);padding:8px 16px;border-radius:8px;opacity:0;transition:opacity .2s}
.toast div.show{opacity:.95}
"""

_BODY = r"""
<header>
  <div class="bar">
    <img class="logo" src="__ICON__" alt="">
    <div>
      <div class="title">SyncPulse Scale Bridge <span class="sub ltr" id="ver"></span></div>
      <div class="sub" data-t="tagline"></div>
    </div>
    <div class="spacer"></div>
    <span class="pill brand" data-t="built_for"></span>
    <span class="pill hidden" id="simPill" data-t="simulation"></span>
    <button class="btn" id="langBtn" type="button"></button>
  </div>
  <nav id="tabs">
    <button data-tab="scales" data-t="tab_scales"></button>
    <button data-tab="find" data-t="tab_find"></button>
    <button data-tab="connect" data-t="tab_connect"></button>
    <button data-tab="manual" data-t="tab_manual"></button>
    <button data-tab="protocols" data-t="tab_protocols"></button>
    <button data-tab="about" data-t="tab_about"></button>
  </nav>
</header>
<main>
  <section id="p-scales"></section>
  <section id="p-find" class="hidden"></section>
  <section id="p-connect" class="hidden"></section>
  <section id="p-manual" class="hidden"></section>
  <section id="p-protocols" class="hidden"></section>
  <section id="p-about" class="hidden"></section>
</main>
<footer><div class="bar" id="sign"></div></footer>
<div class="toast"><div id="toast"></div></div>
"""

_SCRIPT = r"""
const ABOUT = __ABOUT__;
const T = {
en:{
 tagline:'Finds the scale on any COM port, shows the live weight and serves it to your network.',
 built_for:'Built for the SyncPulse platform', simulation:'Simulation', lang:'فارسی',
 tab_scales:'Scales', tab_find:'Find my scale', tab_connect:'Connect to SyncPulse', tab_manual:'Manual & monitor',
 tab_protocols:'Protocols', tab_about:'About',
 no_scales:'No scale saved yet.', no_scales_hint:'Plug the scale into this PC and let the program find it.',
 find_now:'Find my scale', stable:'stable', moving:'moving', no_data:'no data', stale:'old reading',
 overload:'overload', delete:'Delete', confirm_delete:'Delete the profile "{name}"?',
 net:'net', gross:'gross', age:'{ms} ms ago', copied:'Copied', copy:'Copy', address_for:'Address for other systems',
 find_title:'Find the scale automatically',
 find_intro:'The program listens to each port at every common speed, then asks the scale in the languages of the major manufacturers. Only read-only requests are sent: it never zeroes, tares or prints.',
 ports:'COM ports', no_ports:'No COM port on this PC. Plug in the USB-serial adapter and check its driver in Device Manager.',
 refresh:'Refresh', thorough:'Thorough search (more speeds and framings, slower)',
 wait_print:'The scale sends only when Print is pressed (e.g. wired to a label printer) — wait for me to press it',
 listen_only:'Listen only — never send anything to the scale',
 log_press_print:'{port}: ▶ press PRINT on the scale now — listening at {baud} for {seconds} s',
 log_print_wrong_speed:'{port}: data at {baud} was not readable — press PRINT again (trying the next speed)',
 log_print_timeout:'{port}: nothing arrived while waiting for Print',
 mode_print:'sends when Print is pressed', printed:'printed {ago}', last_labels:'Last printed labels',
 listening_all_day:'Listening all the time: every printed label is recorded.',
 ago_s:'{n} s ago', ago_m:'{n} min ago', ago_h:'{n} h ago', no_labels:'No label printed yet.',
 start:'Start search', cancel:'Cancel', running:'Searching…', results:'Results',
 found_on:'Scale found on {port}', not_found_on:'No scale recognised on {port}', confidence:'confidence',
 protocol:'Protocol', line:'Line', mode:'Mode', reading:'Reading', sample:'What arrived',
 mode_continuous:'sends by itself', mode_poll:'answers a request', save_as:'Save as', label:'Description',
 save:'Save', saved:'Saved', field_tested:'tested on real hardware',
 heard_unknown:'Readable data arrived at {baud} {framing} but the format is not in the library yet:',
 tips_title:'If nothing is found',
 tip1:'Serial output must be switched on in the indicator\'s menu (often called COM, rS, SEr, Serial, Continuous or On request).',
 tip2:'Check the cable: many indicators need a null-modem (crossed) cable, some a straight one. Pins 2, 3 and 5 are enough.',
 tip3:'Put something on the scale or press its Print key while searching — some indicators only send then.',
 tip4:'Try the thorough search, or use “Manual & monitor” to watch the raw bytes.',
 ch340:'Driver warning', bt:'Bluetooth — skipped unless ticked',
 log_port_start:'Searching {port}…', log_listen:'{port}: listening at {baud} {framing}',
 log_heard:'{port}: {bytes} bytes at {baud} ({readable}% readable)',
 log_seven_bit:'{port}: looks like 7 data bits with parity — listening again as 7E1/7O1',
 log_ask:'{port}: asking {protocol} at {baud} {framing}', log_reply:'{port}: reply to {protocol}: {text}',
 log_found:'✔ {port}: {protocol} at {baud} {framing} — {value} {unit}', log_not_found:'{port}: nothing recognised',
 log_open_failed:'{port}: cannot open — {error}', log_done:'Finished: {found} scale(s) found',
 log_error:'Error: {error}',
 conn_title:'Connect this PC to SyncPulse', conn_intro:'The SyncPulse server reads the scales on this PC over the network. Four things make that work:',
 step_address:'The address of this PC', step_key:'The access key', step_firewall:'An open port in Windows Firewall',
 step_autostart:'Start with Windows (optional, recommended)',
 port_label:'Port', addresses:'Addresses', key_hint:'Only systems that have this key can read the scales. Keep it private.',
 show:'Show', hide:'Hide', new_key:'New key', confirm_key:'Make a new key? Systems using the old key will stop working until you enter the new one.',
 fw_what:'Windows Firewall blocks incoming connections by default, so the SyncPulse server cannot reach port {port} on this PC until a rule allows it. The button below asks Windows for administrator permission (a UAC prompt) and adds the inbound rule “SyncPulse Scale Bridge” for TCP port {port} on all network types. It also removes any block rule Windows added for this program if its “Allow access?” question was cancelled.',
 fw_open:'Open port {port} in the firewall', fw_remove:'Remove the rule', fw_is_open:'Port {port} is open in Windows Firewall.',
 fw_is_closed:'Port {port} is not open yet.', fw_only_from:'Allow only from (server IP, optional)',
 fw_manual:'To do it by hand, run in an administrator Command Prompt:',
 fw_not_windows:'Not on Windows — open TCP port {port} in this system\'s firewall.',
 as_what:'Runs the bridge in the background when the PC starts, before anyone logs in, and restarts it if it stops. Needs administrator permission once.',
 as_on:'Starts with Windows.', as_off:'Does not start with Windows.', as_other:'A task exists but points to another copy of the program.',
 as_enable:'Start with Windows', as_disable:'Stop starting with Windows',
 as_note:'After enabling it, close this window and restart the PC (or keep this window open until then). Opening the program again later shows this page for the background copy.',
 in_syncpulse:'Then, in SyncPulse', in_syncpulse_steps:'Devices → your scale → RS232 connection: bridge address = one of the addresses above, port = {port}, access key = the key above → Data format: “Profile on the bridge” → choose the profile → Test connection.',
 allowed_title:'Allowed clients', allowed_hint:'Leave empty to accept any machine that has the key, or list the SyncPulse server IP addresses (comma separated).',
 config_file:'Settings file', cancelled_uac:'Cancelled at the Windows prompt.', failed:'Failed: {error}', done:'Done',
 manual_title:'Manual settings and raw monitor', manual_intro:'Watch exactly what arrives on a port with the settings you choose. Useful for an unknown indicator, a cable test, or to check a setting.',
 baud:'Speed (baud)', framing:'Framing', request:'Request to send (hex, empty = only listen)', poll:'Every (ms)',
 preset:'Fill the request from a protocol', monitor_start:'Start monitor', monitor_stop:'Stop',
 frames:'Frames', guesses:'Protocols that can read this', none_yet:'Nothing received yet.', open_error:'Port error: {error}',
 save_manual:'Save these settings as a profile', unit_if_missing:'Unit when the scale sends none', output_unit:'Convert to',
 as_sent:'as sent', stable_samples:'Equal readings = stable',
 proto_title:'Protocol library', proto_intro:'Formats the program can read. Tested on real hardware are marked; the others follow the manufacturers\' published formats and are covered by tests with their sample frames. The same data format is used by many other brands.',
 families:'Used by', request_col:'Request', kind:'Type', reference:'Reference',
 kind_continuous:'continuous', kind_poll:'on request', kind_handshake:'handshake', kind_print:'on Print key',
 about_title:'About', about_text:'SyncPulse Scale Bridge connects weighing scales with an RS-232 serial port to computers and networks. Copy the single program file to the PC beside the scale, run it, and it finds the port, the speed and the protocol by itself, shows the live weight and serves it on the local network.',
 about_platform:'It was written for SyncPulse, a platform for digital forms, production records and reporting, where the weight goes straight into the form a worker is filling in. It is free software and works with any other system through its simple HTTP/JSON interface.',
 author:'Author', company:'Company', website:'Website', license:'License', source:'Source code', version:'Version',
 license_text:'Free software under the GNU General Public License v3 or later, with an additional term (section 7(b)): the author attribution shown in the program must be kept in copies and modified versions.',
 made_by:'Made by', err_name:'Choose a name: letters, digits, - or _.', already_saved:'saved as {names}'
},
fa:{
 tagline:'باسکول را روی هر درگاه COM پیدا می‌کند، وزن زنده را نشان می‌دهد و آن را روی شبکه در اختیار می‌گذارد.',
 built_for:'ساخته‌شده برای پلتفرم SyncPulse', simulation:'شبیه‌ساز', lang:'English',
 tab_scales:'باسکول‌ها', tab_find:'پیدا کردن باسکول', tab_connect:'اتصال به SyncPulse', tab_manual:'تنظیم دستی و مانیتور',
 tab_protocols:'پروتکل‌ها', tab_about:'درباره',
 no_scales:'هنوز باسکولی ذخیره نشده است.', no_scales_hint:'باسکول را به این رایانه وصل کنید تا برنامه آن را پیدا کند.',
 find_now:'پیدا کردن باسکول', stable:'پایدار', moving:'در حال تغییر', no_data:'بدون داده', stale:'خوانش قدیمی',
 overload:'بیش از ظرفیت', delete:'حذف', confirm_delete:'پروفایل «{name}» حذف شود؟',
 net:'خالص', gross:'ناخالص', age:'{ms} میلی‌ثانیه پیش', copied:'کپی شد', copy:'کپی', address_for:'نشانی برای سامانه‌های دیگر',
 find_title:'پیدا کردن خودکار باسکول',
 find_intro:'برنامه روی هر درگاه با همه‌ی سرعت‌های رایج گوش می‌دهد و سپس با زبان سازنده‌های اصلی از باسکول وزن می‌خواهد. فقط درخواست‌های خواندنی فرستاده می‌شود: هیچ‌وقت صفر، تار یا چاپ نمی‌کند.',
 ports:'درگاه‌های COM', no_ports:'درگاه COM روی این رایانه نیست. مبدل USB به سریال را وصل کنید و درایور آن را در Device Manager بررسی کنید.',
 refresh:'بازخوانی', thorough:'جستجوی کامل (سرعت‌ها و قالب‌های بیشتر، کندتر)',
 wait_print:'باسکول فقط با زدن کلید چاپ داده می‌فرستد (مثلاً وصل به لیبل‌زن) — منتظر بمان تا چاپ بزنم',
 listen_only:'فقط گوش بده — هیچ چیزی به باسکول فرستاده نشود',
 log_press_print:'{port}: ▶ همین حالا کلید چاپ باسکول را بزنید — گوش دادن با {baud} تا {seconds} ثانیه',
 log_print_wrong_speed:'{port}: داده با سرعت {baud} خوانا نبود — دوباره چاپ بزنید (سرعت بعدی)',
 log_print_timeout:'{port}: در زمان انتظار برای چاپ چیزی نرسید',
 mode_print:'با زدن کلید چاپ می‌فرستد', printed:'چاپ‌شده {ago}', last_labels:'آخرین برچسب‌های چاپ‌شده',
 listening_all_day:'همیشه در حال گوش دادن: هر برچسبی که چاپ شود ثبت می‌شود.',
 ago_s:'{n} ثانیه پیش', ago_m:'{n} دقیقه پیش', ago_h:'{n} ساعت پیش', no_labels:'هنوز برچسبی چاپ نشده است.',
 start:'شروع جستجو', cancel:'لغو', running:'در حال جستجو…', results:'نتیجه',
 found_on:'باسکول روی {port} پیدا شد', not_found_on:'روی {port} باسکولی شناخته نشد', confidence:'اطمینان',
 protocol:'پروتکل', line:'تنظیم خط', mode:'روش', reading:'خوانش', sample:'داده‌ی دریافتی',
 mode_continuous:'خودش پیوسته می‌فرستد', mode_poll:'به درخواست پاسخ می‌دهد', save_as:'ذخیره با نام', label:'توضیح',
 save:'ذخیره', saved:'ذخیره شد', field_tested:'روی دستگاه واقعی آزموده شده',
 heard_unknown:'با {baud} {framing} داده‌ی خوانا رسید اما این قالب هنوز در کتابخانه نیست:',
 tips_title:'اگر چیزی پیدا نشد',
 tip1:'خروجی سریال باید در منوی نمایشگر روشن باشد (معمولاً با نام COM، rS، SEr، Serial، Continuous یا On request).',
 tip2:'کابل را بررسی کنید: بسیاری از نمایشگرها کابل نال‌مودم (ضربدری) و برخی کابل مستقیم می‌خواهند. پایه‌های ۲، ۳ و ۵ کافی است.',
 tip3:'هنگام جستجو چیزی روی باسکول بگذارید یا کلید چاپ را بزنید؛ برخی نمایشگرها فقط در آن لحظه می‌فرستند.',
 tip4:'جستجوی کامل را امتحان کنید یا از «تنظیم دستی و مانیتور» بایت‌های خام را ببینید.',
 ch340:'هشدار درایور', bt:'بلوتوث — مگر تیک بخورد، بررسی نمی‌شود',
 log_port_start:'جستجو در {port}…', log_listen:'{port}: گوش دادن با {baud} {framing}',
 log_heard:'{port}: {bytes} بایت با سرعت {baud} ({readable}٪ خوانا)',
 log_seven_bit:'{port}: به‌نظر ۷ بیت داده با پریتی است — دوباره با 7E1/7O1 گوش می‌دهد',
 log_ask:'{port}: پرسش {protocol} با {baud} {framing}', log_reply:'{port}: پاسخ به {protocol}: {text}',
 log_found:'✔ {port}: {protocol} با {baud} {framing} — {value} {unit}', log_not_found:'{port}: چیزی شناخته نشد',
 log_open_failed:'{port}: باز نمی‌شود — {error}', log_done:'پایان: {found} باسکول پیدا شد',
 log_error:'خطا: {error}',
 conn_title:'اتصال این رایانه به SyncPulse', conn_intro:'سرور SyncPulse از راه شبکه باسکول‌های این رایانه را می‌خواند. برای این کار چهار چیز لازم است:',
 step_address:'نشانی این رایانه', step_key:'کلید دسترسی', step_firewall:'باز بودن درگاه در فایروال ویندوز',
 step_autostart:'اجرا همراه ویندوز (اختیاری، پیشنهادی)',
 port_label:'درگاه', addresses:'نشانی‌ها', key_hint:'فقط سامانه‌هایی که این کلید را دارند می‌توانند باسکول‌ها را بخوانند. آن را محرمانه نگه دارید.',
 show:'نمایش', hide:'پنهان', new_key:'کلید تازه', confirm_key:'کلید تازه ساخته شود؟ سامانه‌هایی که کلید قبلی را دارند تا کلید تازه را وارد نکنید کار نمی‌کنند.',
 fw_what:'فایروال ویندوز به‌طور پیش‌فرض اتصال‌های ورودی را می‌بندد؛ بنابراین تا وقتی قانونی اجازه ندهد، سرور SyncPulse به درگاه {port} این رایانه نمی‌رسد. دکمه‌ی زیر از ویندوز اجازه‌ی مدیر (پنجره‌ی UAC) می‌گیرد و قانون ورودی «SyncPulse Scale Bridge» را برای TCP درگاه {port} روی همه‌ی انواع شبکه می‌سازد. اگر پرسش «Allow access؟» ویندوز لغو شده باشد، قانون مسدودکننده‌ای را هم که ویندوز برای این برنامه ساخته پاک می‌کند.',
 fw_open:'باز کردن درگاه {port} در فایروال', fw_remove:'حذف قانون', fw_is_open:'درگاه {port} در فایروال ویندوز باز است.',
 fw_is_closed:'درگاه {port} هنوز باز نیست.', fw_only_from:'فقط از این نشانی (IP سرور، اختیاری)',
 fw_manual:'برای انجام دستی، در Command Prompt با دسترسی مدیر اجرا کنید:',
 fw_not_windows:'این سیستم ویندوز نیست — درگاه TCP {port} را در فایروال همین سیستم باز کنید.',
 as_what:'پل را هنگام روشن شدن رایانه، پیش از ورود هر کاربر، در پس‌زمینه اجرا می‌کند و اگر بسته شود دوباره راه می‌اندازد. یک‌بار اجازه‌ی مدیر لازم دارد.',
 as_on:'همراه ویندوز اجرا می‌شود.', as_off:'همراه ویندوز اجرا نمی‌شود.', as_other:'وظیفه‌ای هست ولی به نسخه‌ی دیگری از برنامه اشاره می‌کند.',
 as_enable:'اجرا همراه ویندوز', as_disable:'لغو اجرا همراه ویندوز',
 as_note:'پس از فعال کردن، این پنجره را ببندید و رایانه را دوباره راه‌اندازی کنید (یا تا آن زمان این پنجره را باز نگه دارید). اگر بعداً برنامه را باز کنید، همین صفحه برای نسخه‌ی پس‌زمینه باز می‌شود.',
 in_syncpulse:'سپس در SyncPulse', in_syncpulse_steps:'دستگاه‌ها ← باسکول شما ← اتصال RS232: نشانی پل = یکی از نشانی‌های بالا، درگاه = {port}، کلید دسترسی = کلید بالا ← قالب داده: «پروفایل روی پل» ← انتخاب پروفایل ← تست اتصال.',
 allowed_title:'سامانه‌های مجاز', allowed_hint:'خالی بگذارید تا هر دستگاهی که کلید را دارد پذیرفته شود، یا IP سرور(های) SyncPulse را با ویرگول جدا بنویسید.',
 config_file:'فایل تنظیمات', cancelled_uac:'در پنجره‌ی ویندوز لغو شد.', failed:'ناموفق: {error}', done:'انجام شد',
 manual_title:'تنظیم دستی و مانیتور خام', manual_intro:'دقیقاً ببینید با تنظیمی که انتخاب می‌کنید چه چیزی روی درگاه می‌رسد. برای نمایشگر ناشناخته، آزمایش کابل یا بررسی یک تنظیم.',
 baud:'سرعت (baud)', framing:'قالب', request:'درخواست ارسالی (hex؛ خالی = فقط گوش دادن)', poll:'هر (میلی‌ثانیه)',
 preset:'پر کردن درخواست از روی پروتکل', monitor_start:'شروع مانیتور', monitor_stop:'توقف',
 frames:'فریم‌ها', guesses:'پروتکل‌هایی که این داده را می‌خوانند', none_yet:'هنوز چیزی نرسیده است.', open_error:'خطای درگاه: {error}',
 save_manual:'ذخیره‌ی این تنظیم به‌عنوان پروفایل', unit_if_missing:'واحد، وقتی باسکول واحد نمی‌فرستد', output_unit:'تبدیل به',
 as_sent:'همان‌طور که می‌رسد', stable_samples:'تعداد خوانش برابر = پایدار',
 proto_title:'کتابخانه‌ی پروتکل‌ها', proto_intro:'قالب‌هایی که برنامه می‌خواند. موارد آزموده روی دستگاه واقعی علامت دارند؛ بقیه بر پایه‌ی قالب‌های منتشرشده‌ی سازندگان‌اند و با فریم‌های نمونه‌ی همان مستندات آزمایش شده‌اند. بسیاری از برندهای دیگر هم از همین قالب‌ها استفاده می‌کنند.',
 families:'کاربرد', request_col:'درخواست', kind:'نوع', reference:'مرجع',
 kind_continuous:'پیوسته', kind_poll:'با درخواست', kind_handshake:'دست‌دادن', kind_print:'با کلید چاپ',
 about_title:'درباره', about_text:'SyncPulse Scale Bridge باسکول‌های دارای درگاه سریال RS-232 را به رایانه و شبکه وصل می‌کند. تنها فایل برنامه را روی رایانه‌ی کنار باسکول کپی و اجرا کنید؛ درگاه، سرعت و پروتکل را خودش پیدا می‌کند، وزن زنده را نشان می‌دهد و روی شبکه‌ی محلی در اختیار می‌گذارد.',
 about_platform:'این برنامه برای SyncPulse نوشته شده است؛ پلتفرم فرم‌های دیجیتال، سوابق تولید و گزارش‌گیری که وزن را مستقیم در فرمی که کارگر پر می‌کند می‌نشاند. نرم‌افزار آزاد است و با رابط ساده‌ی HTTP/JSON با هر سامانه‌ی دیگری هم کار می‌کند.',
 author:'سازنده', company:'شرکت', website:'وب‌سایت', license:'مجوز', source:'کد منبع', version:'نسخه',
 license_text:'نرم‌افزار آزاد با مجوز GNU GPL نسخه‌ی ۳ یا بالاتر، با یک شرط افزوده (بند ۷(ب)): نام و مشخصات سازنده که در برنامه نمایش داده می‌شود باید در همه‌ی نسخه‌ها و نسخه‌های تغییر یافته حفظ شود.',
 made_by:'ساخته‌ی', err_name:'یک نام انتخاب کنید: حروف انگلیسی، عدد، - یا _.', already_saved:'ذخیره‌شده با نام {names}'
}};

const S = {lang:'en', tab:'scales', state:null, ports:[], protocols:[], job:null, jobSince:0, log:[],
  weights:{}, inflight:{}, showKey:false, monitor:null, monitorData:null, busy:false, sel:null, draft:{}, shownResults:-1, shownLog:0, shownRunning:false};
try { S.lang = localStorage.getItem('sb.lang') || ((navigator.language||'').toLowerCase().startsWith('fa') ? 'fa' : 'en'); } catch (e) {}

const $ = (sel, el = document) => el.querySelector(sel);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function t(key, vars) {
  let s = (T[S.lang] && T[S.lang][key]) ?? T.en[key] ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => vars[k] ?? '');
  return s;
}
function toast(msg) {
  const el = $('#toast'); el.textContent = msg; el.classList.add('show');
  clearTimeout(toast.h); toast.h = setTimeout(() => el.classList.remove('show'), 1800);
}
async function api(path, opts = {}) {
  const headers = {'X-Requested-With': 'ScaleBridge'};
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  let data;
  try {
    const res = await fetch(path, {method: opts.method || (opts.body !== undefined ? 'POST' : 'GET'), headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined, cache: 'no-store'});
    try { data = await res.json(); } catch (e) { data = {ok: false, error: 'HTTP ' + res.status}; }
    if (!res.ok) data.ok = false;
  } catch (e) { data = {ok: false, error: String(e.message || e)}; }
  return data;
}
async function copy(text) {
  try { await navigator.clipboard.writeText(text); } catch (e) {
    const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (e2) {} ta.remove();
  }
  toast(t('copied'));
}
function fmtValue(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v); if (!isFinite(n)) return esc(v);
  return n.toLocaleString('en-US', {maximumFractionDigits: 6});
}
function protoName(id) { const p = S.protocols.find(x => x.id === id); return p ? p.name : id; }
function slug(s) { return String(s || '').replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^[-_]+|[-_]+$/g, '').toLowerCase().slice(0, 40) || 'scale'; }
function lineText(serial) { return serial ? `${serial.baudrate} ${serial.bytesize}${serial.parity}${serial.stopbits}` : ''; }

// ---------------------------------------------------------------- chrome
function applyLang() {
  document.documentElement.lang = S.lang;
  document.documentElement.dir = S.lang === 'fa' ? 'rtl' : 'ltr';
  document.querySelectorAll('[data-t]').forEach(el => { el.textContent = t(el.dataset.t); });
  $('#langBtn').textContent = t('lang');
  $('#ver').textContent = 'v' + ABOUT.version;
  $('#sign').innerHTML = `<span>${esc(t('made_by'))} <b>${esc(ABOUT.author)}</b> · ${esc(ABOUT.company)}</span>
    <a href="${esc(ABOUT.website)}" target="_blank" rel="noopener">${esc(ABOUT.website.replace(/^https?:\/\//, ''))}</a>
    <a href="${esc(ABOUT.github)}" target="_blank" rel="noopener">GitHub</a>
    <a href="${esc(ABOUT.linkedin)}" target="_blank" rel="noopener">LinkedIn</a>
    <a href="${esc(ABOUT.repository)}" target="_blank" rel="noopener">${esc(t('source'))}</a>
    <span>${esc(ABOUT.license)}</span>`;
  renderAll();
}
function setTab(tab) {
  S.tab = tab;
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
  document.querySelectorAll('main > section').forEach(s => s.classList.toggle('hidden', s.id !== 'p-' + tab));
  if (tab !== 'manual') stopMonitor();
  if (tab === 'find') loadPorts();
  if (location.hash !== '#' + tab) history.replaceState(null, '', '#' + tab);
  renderAll();
}
function renderAll(keepFind) {
  renderScales(); if (keepFind) paintResults(); else renderFind();
  renderConnect(); renderManual(); renderProtocols(); renderAbout();
}

// ---------------------------------------------------------------- scales
function renderScales() {
  const el = $('#p-scales'); if (!S.state) { el.innerHTML = ''; return; }
  const profiles = S.state.profiles || [];
  if (!profiles.length) {
    el.innerHTML = `<div class="card empty"><h2>${esc(t('no_scales'))}</h2><p>${esc(t('no_scales_hint'))}</p>
      <p><button class="btn primary" data-go="find">${esc(t('find_now'))}</button></p></div>`;
    return;
  }
  const ip = (S.state.addresses || [])[0] || '127.0.0.1';
  el.innerHTML = '<div class="grid">' + profiles.map(p => `
    <div class="card" data-profile="${esc(p.name)}">
      <div class="row"><h2 class="wrap">${esc(p.label || p.name)}</h2><div class="spacer"></div>
        <span class="tag ltr">${esc(p.port)}</span></div>
      <div class="weight" id="w-${esc(p.name)}">—</div>
      <div class="state" id="s-${esc(p.name)}"><span class="dot"></span><span>${esc(t('no_data'))}</span></div>
      <div class="kv small" id="f-${esc(p.name)}" style="margin-top:8px"></div>
      ${isPrint(p) ? `<p class="small muted" style="margin:8px 0 0">${esc(t('listening_all_day'))}</p>
        <details style="margin-top:6px"><summary class="small">${esc(t('last_labels'))}</summary><div class="small" id="l-${esc(p.name)}"></div></details>` : ''}
      <div class="kv small" style="margin-top:10px">
        <b>${esc(t('protocol'))}</b><span><bdi>${esc(protoName(p.protocol))}</bdi></span>
        <b>${esc(t('line'))}</b><span class="mono">${esc(lineText(p.serial))}</span>
      </div>
      <div class="small muted" style="margin-top:8px">${esc(t('address_for'))}</div>
      <div class="row" style="gap:6px;flex-wrap:nowrap"><span class="mono wrap ltr" style="flex:1">http://${esc(ip)}:${esc(S.state.listen_port)}/weight?profile=${esc(p.name)}</span>
        <button class="btn small" style="padding:2px 8px" data-copy="http://${esc(ip)}:${esc(S.state.listen_port)}/weight?profile=${esc(p.name)}">${esc(t('copy'))}</button></div>
      <div class="row" style="margin-top:10px"><span class="small muted mono">${esc(p.name)}</span><div class="spacer"></div>
        <button class="btn danger" data-del="${esc(p.name)}">${esc(t('delete'))}</button></div>
    </div>`).join('') + '</div>';
  profiles.forEach(p => paintWeight(p.name));
}
function paintWeight(name) {
  const w = S.weights[name]; const vEl = document.getElementById('w-' + name); const sEl = document.getElementById('s-' + name);
  if (!vEl || !sEl) return;
  if (!w) return;
  if (!w.ok) {
    vEl.innerHTML = '—';
    sEl.innerHTML = `<span class="dot bad"></span><span class="wrap">${esc(w.error || t('no_data'))}</span>`;
    return;
  }
  vEl.innerHTML = w.overload && (w.value === null || w.value === undefined) ? esc(t('overload'))
    : `${fmtValue(w.value)}<small>${esc(w.unit || '')}</small>`;
  const fEl = document.getElementById('f-' + name);
  if (fEl) fEl.innerHTML = Object.entries(w.fields || {}).filter(([k]) => k !== 'barcode')
    .map(([k, v]) => `<b class="ltr">${esc(k)}</b><span class="mono">${esc(v)}</span>`).join('');
  let cls = 'warn', label = t('moving');
  const profile = (S.state.profiles || []).find(p => p.name === name);
  if (profile && isPrint(profile)) { cls = 'ok'; label = t('printed', {ago: ago(w.age_ms)}); }
  else if (w.stale) { cls = ''; label = t('stale'); } else if (w.stable) { cls = 'ok'; label = t('stable'); }
  const extra = w.net === true ? ' · ' + t('net') : (w.net === false ? ' · ' + t('gross') : '');
  sEl.innerHTML = `<span class="dot ${cls}"></span><span>${esc(label + extra)}</span>`;
}
function isPrint(p) { const proto = S.protocols.find(x => x.id === p.protocol); return !!(proto && proto.kind === 'print'); }
function ago(ms) {
  const s = Math.max(0, Math.round((ms || 0) / 1000));
  return s < 90 ? t('ago_s', {n: s}) : (s < 5400 ? t('ago_m', {n: Math.round(s / 60)}) : t('ago_h', {n: Math.round(s / 3600)}));
}
async function paintLabels(name) {
  const el = document.getElementById('l-' + name); if (!el) return;
  const r = await api('/api/labels?profile=' + encodeURIComponent(name) + '&limit=8');
  if (!r.ok) return;
  el.innerHTML = r.labels.length ? '<table><tbody>' + r.labels.slice().reverse().map(l => `<tr>
    <td class="mono">${esc(l.at.slice(11, 19))}</td><td class="mono"><b>${fmtValue(l.value)}</b> ${esc(l.unit)}</td>
    <td class="small">${esc(Object.entries(l.fields || {}).filter(([k]) => !['barcode', 'date', 'time'].includes(k)).map(([k, v]) => k + ': ' + v).join(' · '))}</td></tr>`).join('') + '</tbody></table>'
    : `<p class="muted">${esc(t('no_labels'))}</p>`;
}
async function pollWeights() {
  if (S.tab === 'scales' && S.state && !document.hidden) {
    for (const p of S.state.profiles || []) {
      if (S.inflight[p.name]) continue;
      S.inflight[p.name] = true;
      // A print-only scale is silent between labels: show the last label, however old.
      const extra = isPrint(p) ? '&wait_ms=200&max_age_ms=60000000' : '&wait_ms=1500';
      api('/api/weight?profile=' + encodeURIComponent(p.name) + extra).then(r => {
        S.weights[p.name] = r; paintWeight(p.name);
        if (isPrint(p)) return paintLabels(p.name);
      }).finally(() => { S.inflight[p.name] = false; });
    }
  }
  setTimeout(pollWeights, 700);
}

// ---------------------------------------------------------------- find
async function loadPorts() {
  const r = await api('/api/ports');
  if (r.ok) { S.ports = r.ports; renderFind(); }
}
function renderFind() {
  const el = $('#p-find'); if (!S.state) return;
  const job = S.job; const running = job && job.running;
  const checked = S.sel || new Set(S.ports.filter(p => p.kind !== 'bluetooth').map(p => p.device));
  const thorough = $('#thorough') ? $('#thorough').checked : false;
  const waitPrint = $('#waitPrint') ? $('#waitPrint').checked : false;
  const listenOnly = $('#listenOnly') ? $('#listenOnly').checked : false;
  const ports = S.ports.length ? S.ports.map(p => `
    <label class="check"><input type="checkbox" name="port" value="${esc(p.device)}" ${checked.has(p.device) ? 'checked' : ''} ${running ? 'disabled' : ''}>
      <span><b class="ltr">${esc(p.device)}</b> <span class="muted">${esc(p.description || '')}</span>
      ${p.kind === 'bluetooth' ? `<br><span class="tag warn">${esc(t('bt'))}</span>` : ''}
      ${p.note ? `<br><span class="tag warn">${esc(t('ch340'))}</span> <span class="small muted">${esc(p.note)}</span>` : ''}</span></label>`).join('')
    : `<p class="note warn">${esc(t('no_ports'))}</p>`;
  el.innerHTML = `
    <div class="card"><h2>${esc(t('find_title'))}</h2><p class="muted">${esc(t('find_intro'))}</p>
      <h3>${esc(t('ports'))}</h3>${ports}
      <div class="row" style="margin-top:10px">
        <label class="row small"><input type="checkbox" id="thorough" ${thorough ? 'checked' : ''} ${running ? 'disabled' : ''}> ${esc(t('thorough'))}</label>
        <label class="row small"><input type="checkbox" id="waitPrint" ${waitPrint ? 'checked' : ''} ${running ? 'disabled' : ''}> ${esc(t('wait_print'))}</label>
        <label class="row small"><input type="checkbox" id="listenOnly" ${listenOnly ? 'checked' : ''} ${running ? 'disabled' : ''}> ${esc(t('listen_only'))}</label>
        <div class="spacer"></div>
        <button class="btn" id="refreshPorts" ${running ? 'disabled' : ''}>${esc(t('refresh'))}</button>
        ${running ? `<button class="btn danger" id="cancelDetect">${esc(t('cancel'))}</button>`
                  : `<button class="btn primary" id="startDetect" ${S.ports.length ? '' : 'disabled'}>${esc(t('start'))}</button>`}
      </div>
      <div id="findStatus"></div>
    </div>
    <div id="findResults"></div>`;
  S.shownResults = -1; S.shownRunning = running;
  paintProgress(); paintResults();
}
function logLine(e) {
  const cls = e.code === 'found' ? 'found' : (e.code === 'open_failed' || e.code === 'error' ? 'bad' : '');
  const vars = {...e, protocol: e.protocol ? protoName(e.protocol) : '', readable: e.readable !== undefined ? Math.round(e.readable * 100) : ''};
  return `<div class="${cls}"><span class="muted mono">${esc(Number(e.t).toFixed(1))}s</span> ${esc(t('log_' + e.code, vars))}</div>`;
}
function paintProgress() {
  const box = $('#findStatus'); const job = S.job; if (!box) return;
  if (!job) { box.innerHTML = ''; return; }
  const pct = Math.round((job.progress || 0) * 100);
  if (!$('#log')) {
    box.innerHTML = `<div style="margin-top:12px"><div class="row small muted"><span id="jobText"></span><div class="spacer"></div><span class="mono" id="jobPct"></span></div>
      <div class="progress"><div id="jobBar"></div></div><div class="log" id="log" style="margin-top:8px"></div></div>`;
    S.shownLog = 0;
  }
  $('#jobText').textContent = job.running ? t('running') : t('done');
  $('#jobPct').textContent = `${pct}% · ${job.elapsed_s}s`;
  $('#jobBar').style.width = pct + '%';
  const logEl = $('#log');
  const start = Math.max(S.shownLog || 0, S.log.length - 250);
  if (start < S.log.length) {
    logEl.insertAdjacentHTML('beforeend', S.log.slice(start).map(logLine).join(''));
    S.shownLog = S.log.length;
    while (logEl.childElementCount > 250) logEl.firstElementChild.remove();
    logEl.scrollTop = logEl.scrollHeight;
  }
}
function paintResults() {
  const box = $('#findResults'); const job = S.job; if (!box) return;
  const results = job ? (job.results || []) : [];
  const key = results.length + ':' + (job && job.running ? 1 : 0) + ':' + (S.state.profiles || []).length;
  if (S.shownResults === key) return;
  S.shownResults = key;
  box.innerHTML = (results.length ? `<h3>${esc(t('results'))}</h3>${results.map(renderResult).join('')}` : '')
    + (job && !job.running && !results.some(r => r.found) ? tipsCard() : '');
}
function tipsCard() {
  return `<div class="card"><h3>${esc(t('tips_title'))}</h3><ul class="steps">
    <li>${esc(t('tip1'))}</li><li>${esc(t('tip2'))}</li><li>${esc(t('tip3'))}</li><li>${esc(t('tip4'))}</li></ul></div>`;
}
function renderResult(r) {
  if (!r.found) {
    const u = r.unknown;
    return `<div class="card"><h2>${esc(t('not_found_on', {port: r.port}))}</h2>
      ${r.error ? `<p class="note warn">${esc(r.error)}</p>` : ''}
      ${u ? `<p class="muted">${esc(t('heard_unknown', {baud: u.baud, framing: u.framing}))}</p>
        <div class="log mono">${esc(u.sample_text)}</div><div class="log mono small" style="margin-top:6px">${esc(u.sample_hex)}</div>` : ''}</div>`;
  }
  const rd = r.reading || {};
  const d = S.draft[r.port] || {};
  const same = (S.state.profiles || []).filter(p => p.port === r.port && p.protocol === r.protocol).map(p => p.name);
  return `<div class="card">
    <div class="row"><h2>${esc(t('found_on', {port: r.port}))}</h2><div class="spacer"></div>
      <span class="tag">${esc(t('confidence'))} ${Math.round((r.confidence || 0) * 100)}%</span>
      ${r.field_tested ? `<span class="tag">${esc(t('field_tested'))}</span>` : ''}</div>
    <div class="kv" style="margin-top:8px">
      <b>${esc(t('protocol'))}</b><span><bdi>${esc(r.protocol_name)}</bdi></span>
      <b>${esc(t('line'))}</b><span class="mono">${esc(r.port)} · ${esc(lineText(r.serial))}${r.exchange && r.exchange.request_hex ? ' · ' + esc(r.exchange.request_hex) : ''}</span>
      <b>${esc(t('mode'))}</b><span>${esc(t('mode_' + r.mode))}</span>
      <b>${esc(t('reading'))}</b><span class="mono">${fmtValue(rd.value)} ${esc(rd.unit || '')}${rd.stable === true ? ' · ' + esc(t('stable')) : (rd.stable === false ? ' · ' + esc(t('moving')) : '')}</span>
      <b>${esc(t('sample'))}</b><span class="mono wrap">${esc(r.sample_text)}</span>
    </div>
    <div class="row" style="margin-top:12px">
      <label class="f">${esc(t('save_as'))}<input class="ltr" data-name="${esc(r.port)}" value="${esc(d.name ?? slug('scale-' + r.port))}" size="18"></label>
      <label class="f">${esc(t('label'))}<input data-label="${esc(r.port)}" value="${esc(d.label ?? '')}" size="22"></label>
      ${rd.unit ? '' : `<label class="f">${esc(t('unit_if_missing'))}<select data-unit="${esc(r.port)}">${['kg','g','t','lb'].map(u => `<option ${d.unit === u ? 'selected' : ''}>${u}</option>`).join('')}</select></label>`}
      <div class="spacer"></div>
      ${same.length ? `<span class="tag">${esc(t('already_saved', {names: same.join(', ')}))}</span>` : ''}
      <button class="btn primary" data-save-result="${esc(r.port)}">${esc(t('save'))}</button>
    </div></div>`;
}
async function startDetect() {
  const ports = [...document.querySelectorAll('input[name=port]:checked')].map(i => i.value);
  if (!ports.length) return;
  S.log = []; S.jobSince = 0; S.draft = {};
  const r = await api('/api/detect', {body: {ports, thorough: $('#thorough').checked, bluetooth: true,
    print_wait_s: $('#waitPrint').checked ? 60 : 0, listen_only: $('#listenOnly').checked}});
  if (!r.ok) { toast(t('failed', {error: r.error})); return; }
  S.job = r.job; renderFind(); setTimeout(pollDetect, 300);
}
async function pollDetect() {
  const r = await api('/api/detect?since=' + S.jobSince);
  if (r.ok && r.job) {
    S.log.push(...r.job.log); S.jobSince = r.job.log_size; S.job = r.job;
    if (S.shownRunning !== r.job.running) renderFind(); else { paintProgress(); paintResults(); }
    if (r.job.running) { setTimeout(pollDetect, 500); } else { refreshState(); }
  }
}
async function saveResult(port) {
  const r = (S.job.results || []).find(x => x.port === port); if (!r) return;
  const name = document.querySelector(`[data-name="${CSS.escape(port)}"]`).value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$/.test(name)) { toast(t('err_name')); return; }
  const label = document.querySelector(`[data-label="${CSS.escape(port)}"]`).value.trim();
  const unitEl = document.querySelector(`[data-unit="${CSS.escape(port)}"]`);
  const res = await api('/api/profiles', {body: {detection: r, name, label, unit: unitEl ? unitEl.value : ''}});
  if (!res.ok) { toast(t('failed', {error: res.error})); return; }
  S.state.profiles = res.profiles; toast(t('saved')); renderAll();
}

// ---------------------------------------------------------------- connect
function renderConnect() {
  const el = $('#p-connect'); const st = S.state; if (!st) return;
  const port = st.listen_port; const fw = st.firewall || {}; const as = st.autostart || {};
  const key = S.showKey ? st.token : '•'.repeat(Math.min(24, (st.token || '').length));
  const addr = (st.addresses || []).map(a => `<span class="tag ltr">${esc(a)}</span>`).join(' ') || '<span class="muted">—</span>';
  const fwCmd = `netsh advfirewall firewall add rule name="SyncPulse Scale Bridge" dir=in action=allow protocol=TCP localport=${port} profile=any`;
  el.innerHTML = `
    <div class="card"><h2>${esc(t('conn_title'))}</h2><p class="muted">${esc(t('conn_intro'))}</p></div>
    <div class="card"><h3><span class="num">1</span>${esc(t('step_address'))}</h3>
      <div class="kv"><b>${esc(t('addresses'))}</b><span>${addr}</span><b>${esc(t('port_label'))}</b><span class="mono">${esc(port)}</span>
      <b>Host</b><span class="mono">${esc(st.host)}</span></div></div>
    <div class="card"><h3><span class="num">2</span>${esc(t('step_key'))}</h3>
      <div class="row"><span class="mono wrap" style="font-size:14px">${esc(key)}</span><div class="spacer"></div>
        <button class="btn" id="keyShow">${esc(S.showKey ? t('hide') : t('show'))}</button>
        <button class="btn" id="keyCopy">${esc(t('copy'))}</button>
        <button class="btn danger" id="keyNew">${esc(t('new_key'))}</button></div>
      <p class="small muted">${esc(t('key_hint'))}</p></div>
    <div class="card"><h3><span class="num">3</span>${esc(t('step_firewall'))}</h3>
      ${fw.supported === false ? `<p>${esc(t('fw_not_windows', {port}))}</p>` : `
      <p class="${fw.port_ok ? 'note' : 'note warn'}"><span class="dot ${fw.port_ok ? 'ok' : 'warn'}"></span> ${esc(fw.port_ok ? t('fw_is_open', {port}) : t('fw_is_closed', {port}))}</p>
      <p class="small">${esc(t('fw_what', {port}))}</p>
      <div class="row"><label class="f">${esc(t('fw_only_from'))}<input class="ltr" id="fwRemote" placeholder="192.168.1.10" size="16"></label>
        <div class="spacer"></div>
        ${fw.exists ? `<button class="btn" id="fwRemove">${esc(t('fw_remove'))}</button>` : ''}
        <button class="btn primary" id="fwOpen">${esc(t('fw_open', {port}))}</button></div>
      <p class="small muted" style="margin-top:10px">${esc(t('fw_manual'))}</p><div class="log mono small">${esc(fwCmd)}</div>`}
    </div>
    <div class="card"><h3><span class="num">4</span>${esc(t('step_autostart'))}</h3>
      ${as.supported === false ? '' : `
      <p class="${as.enabled && as.this_program ? 'note' : 'note warn'}"><span class="dot ${as.enabled ? (as.this_program ? 'ok' : 'warn') : ''}"></span>
        ${esc(as.enabled ? (as.this_program ? t('as_on') : t('as_other')) : t('as_off'))}</p>
      <p class="small">${esc(t('as_what'))}</p>
      <div class="row"><div class="spacer"></div>
        ${as.enabled ? `<button class="btn" id="asOff">${esc(t('as_disable'))}</button>` : ''}
        ${!as.enabled || !as.this_program ? `<button class="btn primary" id="asOn">${esc(t('as_enable'))}</button>` : ''}</div>
      <p class="small muted">${esc(t('as_note'))}</p>`}
    </div>
    <div class="card"><h3>${esc(t('in_syncpulse'))}</h3><p>${esc(t('in_syncpulse_steps', {port}))}</p></div>
    <div class="card"><h3>${esc(t('allowed_title'))}</h3><p class="small muted">${esc(t('allowed_hint'))}</p>
      <div class="row"><input class="ltr" id="allowed" style="flex:1" value="${esc((st.allowed_clients || []).join(', '))}">
      <button class="btn" id="allowedSave">${esc(t('save'))}</button></div>
      <p class="small muted" style="margin-top:10px">${esc(t('config_file'))}: <span class="mono wrap">${esc(st.config_path)}</span></p></div>`;
}
async function adminAction(path, body) {
  S.busy = true; document.body.style.cursor = 'progress';
  const r = await api(path, {body});
  S.busy = false; document.body.style.cursor = '';
  if (r.state) S.state = r.state;
  toast(r.ok ? t('done') : (r.cancelled ? t('cancelled_uac') : t('failed', {error: r.error || ('code ' + r.code)})));
  renderAll();
}

// ---------------------------------------------------------------- manual
function renderManual() {
  const el = $('#p-manual'); if (!S.state) return;
  if (el.dataset.ready === S.lang + S.ports.length + S.protocols.length) { paintMonitor(); return; }
  const keep = {};
  el.querySelectorAll('[id^=m-]').forEach(i => { keep[i.id] = i.value; });
  const bauds = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200];
  const framings = ['8N1', '7E1', '7O1', '8E1', '8O1', '8N2', '7N2'];
  el.innerHTML = `
    <div class="card"><h2>${esc(t('manual_title'))}</h2><p class="muted">${esc(t('manual_intro'))}</p>
      <div class="row">
        <label class="f">${esc(t('port_label'))}<select id="m-port">${S.ports.map(p => `<option value="${esc(p.device)}">${esc(p.device)}</option>`).join('')}</select></label>
        <label class="f">${esc(t('baud'))}<select id="m-baud">${bauds.map(b => `<option ${b === 9600 ? 'selected' : ''}>${b}</option>`).join('')}</select></label>
        <label class="f">${esc(t('framing'))}<select id="m-framing">${framings.map(f => `<option>${f}</option>`).join('')}</select></label>
        <label class="f">${esc(t('preset'))}<select id="m-proto"><option value="">—</option>${S.protocols.filter(p => !p.id.startsWith('custom')).map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</select></label>
      </div>
      <div class="row" style="margin-top:8px">
        <label class="f" style="flex:1">${esc(t('request'))}<input class="ltr mono" id="m-request" placeholder="53 49 0D 0A"></label>
        <label class="f">${esc(t('poll'))}<input class="ltr" id="m-poll" type="number" min="100" max="10000" step="100" value="500" style="width:90px"></label>
        <button class="btn primary" id="monBtn"></button>
      </div>
      <div id="monOut" style="margin-top:12px"></div>
    </div>
    <div class="card"><h3>${esc(t('save_manual'))}</h3>
      <div class="row">
        <label class="f">${esc(t('save_as'))}<input class="ltr" id="m-name" value="scale-1" size="16"></label>
        <label class="f">${esc(t('label'))}<input id="m-label" size="20"></label>
        <label class="f">${esc(t('protocol'))}<select id="m-sproto">${S.protocols.map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</select></label>
        <label class="f">${esc(t('unit_if_missing'))}<select id="m-unit"><option value="">—</option>${['kg','g','t','lb','oz'].map(u => `<option>${u}</option>`).join('')}</select></label>
        <label class="f">${esc(t('output_unit'))}<select id="m-ounit"><option value="">${esc(t('as_sent'))}</option>${['kg','g','t','lb','oz'].map(u => `<option>${u}</option>`).join('')}</select></label>
        <label class="f">${esc(t('stable_samples'))}<input class="ltr" id="m-stable" type="number" min="1" max="20" value="3" style="width:70px"></label>
      </div>
      <div class="row" id="m-custom" style="margin-top:8px"></div>
      <div class="row" style="margin-top:8px"><div class="spacer"></div><button class="btn primary" id="m-save">${esc(t('save'))}</button></div>
    </div>`;
  Object.entries(keep).forEach(([id, v]) => { const i = document.getElementById(id); if (i && v !== undefined) i.value = v; });
  el.dataset.ready = S.lang + S.ports.length + S.protocols.length;
  renderCustom(); paintMonitor();
}
function renderCustom() {
  const box = $('#m-custom'); if (!box) return;
  const id = $('#m-sproto').value;
  if (id === 'custom_binary') {
    box.innerHTML = `<label class="f">pattern (hex, ?? = any)<input class="ltr mono" id="c-pattern" value="58 ?? 07 07"></label>
      <label class="f">value_offset<input class="ltr" id="c-offset" type="number" value="4" style="width:70px"></label>
      <label class="f">value_length<input class="ltr" id="c-length" type="number" value="3" style="width:70px"></label>
      <label class="f">byte_order<select id="c-order"><option>big</option><option>little</option></select></label>
      <label class="row small"><input type="checkbox" id="c-signed"> signed</label>`;
  } else if (id === 'custom_ascii') {
    box.innerHTML = `<label class="f" style="flex:1">regex (group 1 = number)<input class="ltr mono" id="c-regex" value="([-+]?\\d+\\.?\\d*)"></label>`;
  } else box.innerHTML = '';
}
function monitorQuery() {
  const q = new URLSearchParams({port: $('#m-port').value, baud: $('#m-baud').value, framing: $('#m-framing').value,
    request_hex: $('#m-request').value, poll_ms: $('#m-poll').value || '500'});
  const proto = S.protocols.find(p => p.id === $('#m-proto').value);
  if (proto && proto.after_ack_hex) q.set('after_ack_hex', proto.after_ack_hex);
  return q;
}
function startMonitor() {
  stopMonitor(); S.monitorData = null;
  const tick = async () => {
    const r = await api('/api/monitor?' + monitorQuery());
    if (!S.monitor) return;
    S.monitorData = r; paintMonitor();
    S.monitor = setTimeout(tick, 1000);
  };
  S.monitor = setTimeout(tick, 0); paintMonitor();
}
function stopMonitor() { if (S.monitor) { clearTimeout(S.monitor); S.monitor = null; paintMonitor(); } }
function paintMonitor() {
  const btn = $('#monBtn'); const out = $('#monOut'); if (!btn || !out) return;
  btn.textContent = S.monitor ? t('monitor_stop') : t('monitor_start');
  const r = S.monitorData; if (!r) { out.innerHTML = ''; return; }
  if (!r.ok && r.error) { out.innerHTML = `<p class="note warn">${esc(t('open_error', {error: r.error}))}</p>`; return; }
  const frames = (r.frames || []).slice().reverse();
  out.innerHTML = `<div class="small muted mono">${esc(r.settings || '')} · rx ${esc((r.stats || {}).bytes_rx ?? 0)} B</div>
    ${frames.length ? `<table style="margin-top:6px"><thead><tr><th>ms</th><th>HEX</th><th>TEXT</th></tr></thead><tbody>
      ${frames.map(f => `<tr><td class="mono">${esc(f.age_ms)}</td><td class="mono wrap">${esc(f.hex)}</td><td class="mono wrap">${esc(f.text)}</td></tr>`).join('')}</tbody></table>`
      : `<p class="muted">${esc(t('none_yet'))}</p>`}
    ${(r.guesses || []).length ? `<h3>${esc(t('guesses'))}</h3><table><tbody>${r.guesses.map(g => `<tr><td>${esc(g.name)}</td><td class="mono">${fmtValue(g.value)} ${esc(g.unit || '')}</td><td class="muted">×${esc(g.count)}</td></tr>`).join('')}</tbody></table>` : ''}`;
}
async function saveManual() {
  const name = $('#m-name').value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$/.test(name)) { toast(t('err_name')); return; }
  const framing = $('#m-framing').value; const protocol = $('#m-sproto').value;
  const params = {};
  if (protocol === 'custom_binary') Object.assign(params, {pattern: $('#c-pattern').value, value_offset: +$('#c-offset').value,
    value_length: +$('#c-length').value, byte_order: $('#c-order').value, signed: $('#c-signed').checked});
  if (protocol === 'custom_ascii') params.regex = $('#c-regex').value;
  const proto = S.protocols.find(p => p.id === protocol) || {};
  const request = $('#m-request').value.trim();
  const body = {name, label: $('#m-label').value.trim(), port: $('#m-port').value, protocol, params,
    serial: {baudrate: +$('#m-baud').value, bytesize: +framing[0], parity: framing[1], stopbits: +framing[2]},
    exchange: {request_hex: request, after_ack_hex: proto.after_ack_hex || '', poll_interval_ms: +$('#m-poll').value || 500},
    unit: $('#m-unit').value, output_unit: $('#m-ounit').value, stable_samples: +$('#m-stable').value || 3};
  stopMonitor();
  const r = await api('/api/profiles', {body});
  if (!r.ok) { toast(t('failed', {error: r.error})); return; }
  S.state.profiles = r.profiles; toast(t('saved')); renderAll();
}

// ---------------------------------------------------------------- protocols & about
function renderProtocols() {
  const el = $('#p-protocols');
  el.innerHTML = `<div class="card"><h2>${esc(t('proto_title'))}</h2><p class="muted">${esc(t('proto_intro'))}</p>
    <div style="overflow-x:auto"><table><thead><tr><th>${esc(t('protocol'))}</th><th>${esc(t('kind'))}</th><th>${esc(t('request_col'))}</th><th>${esc(t('families'))}</th><th>${esc(t('reference'))}</th></tr></thead><tbody>
    ${S.protocols.map(p => `<tr><td><b><bdi>${esc(p.name)}</bdi></b><br><span class="mono small muted">${esc(p.id)}</span>${p.field_tested ? `<br><span class="tag">${esc(t('field_tested'))}</span>` : ''}</td>
      <td>${esc(t('kind_' + p.kind))}</td><td class="mono small">${esc(p.request_hex || '—')}${p.after_ack_hex ? ' → ' + esc(p.after_ack_hex) : ''}</td>
      <td class="small">${esc(p.families)}</td><td class="small muted">${esc(p.reference)}</td></tr>`).join('')}
    </tbody></table></div></div>`;
}
function renderAbout() {
  const el = $('#p-about'); const a = ABOUT;
  el.innerHTML = `<div class="card"><h2>${esc(t('about_title'))}</h2><p>${esc(t('about_text'))}</p><p>${esc(t('about_platform'))}</p>
    <div class="kv" style="margin-top:12px">
      <b>${esc(t('version'))}</b><span class="mono">${esc(a.version)}</span>
      <b>${esc(t('author'))}</b><span>${esc(a.author)}</span>
      <b>${esc(t('company'))}</b><span>${esc(a.company)}</span>
      <b>${esc(t('website'))}</b><a class="ltr" href="${esc(a.website)}" target="_blank" rel="noopener">${esc(a.website)}</a>
      <b>GitHub</b><a class="ltr" href="${esc(a.github)}" target="_blank" rel="noopener">${esc(a.github)}</a>
      <b>LinkedIn</b><a class="ltr" href="${esc(a.linkedin)}" target="_blank" rel="noopener">${esc(a.linkedin)}</a>
      <b>${esc(t('source'))}</b><a class="ltr" href="${esc(a.repository)}" target="_blank" rel="noopener">${esc(a.repository)}</a>
      <b>${esc(t('license'))}</b><span>${esc(a.license)}</span>
    </div>
    <p class="small muted" style="margin-top:12px">${esc(t('license_text'))}</p>
    <p class="small muted">${esc(a.copyright)}</p></div>`;
}

// ---------------------------------------------------------------- events & boot
document.addEventListener('click', async ev => {
  const b = ev.target.closest('button'); if (!b || b.disabled) return;
  if (b.dataset.tab) return setTab(b.dataset.tab);
  if (b.dataset.go) return setTab(b.dataset.go);
  if (b.id === 'langBtn') { S.lang = S.lang === 'fa' ? 'en' : 'fa'; try { localStorage.setItem('sb.lang', S.lang); } catch (e) {} return applyLang(); }
  if (b.dataset.del) {
    if (!confirm(t('confirm_delete', {name: b.dataset.del}))) return;
    const r = await api('/api/profiles/' + encodeURIComponent(b.dataset.del), {method: 'DELETE'});
    if (r.ok) { S.state.profiles = r.profiles; delete S.weights[b.dataset.del]; renderAll(); } else toast(t('failed', {error: r.error}));
    return;
  }
  if (b.dataset.saveResult) return saveResult(b.dataset.saveResult);
  if (b.dataset.copy) return copy(b.dataset.copy);
  switch (b.id) {
    case 'startDetect': return startDetect();
    case 'cancelDetect': await api('/api/detect/cancel', {body: {}}); return;
    case 'refreshPorts': return loadPorts();
    case 'keyShow': S.showKey = !S.showKey; return renderConnect();
    case 'keyCopy': return copy(S.state.token);
    case 'keyNew':
      if (!confirm(t('confirm_key'))) return;
      { const r = await api('/api/token', {body: {}}); if (r.ok) { S.state.token = r.token; S.showKey = true; renderConnect(); } }
      return;
    case 'fwOpen': return adminAction('/api/firewall', {remote_ip: $('#fwRemote').value.trim()});
    case 'fwRemove': return adminAction('/api/firewall', {remove: true});
    case 'asOn': return adminAction('/api/autostart', {enable: true});
    case 'asOff': return adminAction('/api/autostart', {enable: false});
    case 'allowedSave': {
      const clients = $('#allowed').value.split(/[,\s]+/).filter(Boolean);
      const r = await api('/api/allowed', {body: {clients}});
      if (r.ok) { S.state.allowed_clients = r.allowed_clients; toast(t('saved')); } else toast(t('failed', {error: r.error}));
      return;
    }
    case 'monBtn': return S.monitor ? stopMonitor() : startMonitor();
    case 'm-save': return saveManual();
  }
});
document.addEventListener('input', ev => {
  const el = ev.target; const port = el.dataset && (el.dataset.name || el.dataset.label || el.dataset.unit);
  if (!port) return;
  const d = S.draft[port] = S.draft[port] || {};
  if (el.dataset.name) d.name = el.value; else if (el.dataset.label) d.label = el.value; else d.unit = el.value;
});
document.addEventListener('change', ev => {
  if (ev.target.name === 'port') {
    S.sel = new Set([...document.querySelectorAll('input[name=port]:checked')].map(i => i.value));
  }
  if (ev.target.id === 'm-proto') {
    const p = S.protocols.find(x => x.id === ev.target.value);
    if (p) { $('#m-request').value = p.request_hex; const s = $('#m-sproto'); if (s) { s.value = p.id; renderCustom(); } }
  }
  if (ev.target.id === 'm-sproto') renderCustom();
});
async function refreshState(fresh) {
  const r = await api('/api/state' + (fresh ? '?fresh=1' : ''));
  if (r.ok) {
    S.state = r; $('#simPill').classList.toggle('hidden', !r.simulate);
    const typing = document.activeElement && document.activeElement.closest && document.activeElement.closest('#p-find');
    renderAll(!!typing);
  }
}
async function boot() {
  const [state, protos, ports, job] = await Promise.all([api('/api/state'), api('/api/protocols'), api('/api/ports'), api('/api/detect')]);
  if (protos.ok) S.protocols = protos.protocols;
  if (ports.ok) S.ports = ports.ports;
  if (state.ok) { S.state = state; $('#simPill').classList.toggle('hidden', !state.simulate); }
  if (job.ok && job.job) { S.job = job.job; S.log = job.job.log; S.jobSince = job.job.log_size; if (job.job.running) pollDetect(); }
  applyLang();
  const tab = location.hash.replace('#', '');
  setTab(['scales','find','connect','manual','protocols','about'].includes(tab) ? tab : ((state.profiles || []).length ? 'scales' : 'find'));
  pollWeights();
}
boot();
"""

_REMOTE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SyncPulse Scale Bridge</title>
<link rel="icon" href="__ICON__"><style>body{font:15px/1.6 "Segoe UI",Tahoma,sans-serif;max-width:640px;margin:40px auto;
padding:0 16px;color:#16202a;background:#f4f6f8}.card{background:#fff;border:1px solid #dde3e9;border-radius:12px;padding:20px}
a{color:#0f766e}small{color:#5b6b7a}</style></head><body><div class="card">
<h2>SyncPulse Scale Bridge __VERSION__</h2>
<p>This bridge serves the scales connected to this PC to the network (JSON over HTTP, see
<a href="__REPO__">the documentation</a>). Its control page opens only on the PC itself:
<b>http://127.0.0.1:__PORT__/</b></p>
<p dir="rtl">این پل وزن باسکول‌های وصل به این رایانه را روی شبکه در اختیار می‌گذارد. صفحه‌ی مدیریت فقط روی خود همین رایانه باز می‌شود.</p>
<p><small>__AUTHOR__ · <a href="__WEBSITE__">__WEBSITE__</a> · <a href="__GITHUB__">GitHub</a> ·
<a href="__LINKEDIN__">LinkedIn</a> · __LICENSE__</small></p></div></body></html>"""


def page() -> str:
    head = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="author" content="' + ABOUT["author"] + ' — ' + ABOUT["company"] + '">'
            '<title>SyncPulse Scale Bridge</title><link rel="icon" href="' + ICON + '">'
            '<style>' + _STYLE + '</style></head><body>')
    about = json.dumps(ABOUT, ensure_ascii=False).replace("</", "<\\/")
    return (head + _BODY.replace("__ICON__", ICON)
            + "<script>" + _SCRIPT.replace("__ABOUT__", about) + "</script></body></html>")


def remote_page(port: int = 8765) -> str:
    values = {"__ICON__": ICON, "__VERSION__": ABOUT["version"], "__REPO__": ABOUT["repository"],
              "__PORT__": str(port), "__AUTHOR__": f'{ABOUT["author"]} — {ABOUT["company"]}',
              "__WEBSITE__": ABOUT["website"], "__GITHUB__": ABOUT["github"],
              "__LINKEDIN__": ABOUT["linkedin"], "__LICENSE__": ABOUT["license"]}
    html = _REMOTE
    for k, v in values.items():
        html = html.replace(k, v)
    return html
