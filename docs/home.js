/* "Add to Home Screen": a button in the masthead on phones and tablets. The same file is copied into each sister
   site (la-streets: USC Street Parking, LA Street Rules and its neighborhood pages; sf-streets; curb-log; la-walking),
   so keep the copies alike. Each page's <link rel="manifest"> names its app, and the <script> tag's data-app is the
   name the steps use.
   - Android (Chrome, Edge, Samsung Internet): the browser installs the page itself when the button asks it to.
   - iPhone and iPad: no browser lets a page do that (WebKit has said it won't), so the button shows the steps for
     the browser in use.
   - Hidden on computers and when the page is already open from the Home Screen. */
(() => {
  const me = document.currentScript, app = me?.dataset.app || document.title;
  const mast = document.querySelector('.mast .end');
  // Safari's web apps report display-mode "fullscreen" for a "standalone" manifest (WebKit bug 264218), so check them all
  const fromHome = () => navigator.standalone === true
    || matchMedia('(display-mode: standalone), (display-mode: fullscreen), (display-mode: minimal-ui)').matches;
  if (fromHome()) {
    // Opened from the Home Screen, the page can come back from memory days later still showing that day's "Today"
    // line and data. Load it again when it comes back on another day or after 3 hours (the #block link stays), but
    // only with a connection: offline, a reload would swap the page for the browser's error page.
    const opened = Date.now(), day = new Date().toDateString();
    const fresh = () => {
      if (document.visibilityState === 'visible' && navigator.onLine
          && (new Date().toDateString() !== day || Date.now() - opened > 3 * 3600e3)) location.reload();
    };
    document.addEventListener('visibilitychange', fresh);
    addEventListener('online', fresh);
    addEventListener('pageshow', e => { if (e.persisted) fresh(); });
    return;
  }
  if (!mast) return;

  const ua = navigator.userAgent;
  // iPads say "Macintosh", and so does an iPhone set to Request Desktop Website; the screen tells them apart
  const touchMac = /Macintosh/.test(ua) && navigator.maxTouchPoints > 1;
  const ipad = /iPad/.test(ua) || (touchMac && Math.min(screen.width, screen.height) >= 600);
  const ios = ipad || touchMac || /iPhone|iPod/.test(ua);
  // big Android tablets ask for desktop sites by default, with a Linux user agent ("X11; CrOS" is a Chromebook)
  const android = /Android/.test(ua) || (/X11; Linux/.test(ua) && navigator.maxTouchPoints > 1 && matchMedia('(pointer: coarse)').matches);
  // the steps open in a <dialog>, which iOS has only from 15.4; without it, no button rather than one that does nothing
  if ((!ios && !android) || typeof HTMLDialogElement !== 'function') return;
  // apps that open links in their own browser, which can't add pages to the Home Screen: on iOS every real browser's
  // user agent has "Safari/" and an app's own web view doesn't (Google's app does, so it's named); on Android, "; wv)"
  const inApp = /FBAN|FBAV|FB_IAB|Instagram|LinkedInApp|MicroMessenger|Snapchat|TikTok|musical_ly|Twitter|Line\/|GSA\//.test(ua)
    || (ios ? !/Safari\//.test(ua) : /; wv\)/.test(ua));
  const browser = inApp ? 'inapp' : !ios ? 'android' : /CriOS/.test(ua) ? 'chrome' : /FxiOS/.test(ua) ? 'firefox'
    : /EdgiOS/.test(ua) ? 'edge' : /OPiOS|DuckDuckGo|YaBrowser/.test(ua) ? 'other' : 'safari';
  // Safari 26 (Sept 2025) moved Share into the ••• "More" menu and added "Open as Web App"; Safari 27 renamed that
  // button "Page Menu" and gave it a new icon. The user agent's iOS version is frozen at 18, but Version/ is right.
  const safariV = browser === 'safari' ? +(ua.match(/Version\/(\d+)/) || [])[1] || 0 : 0;

  // Android: hold the browser's own install prompt for the button (and keep its banner from popping up on its own).
  // Chrome offers it only after a tap and about 30 seconds on the page; until then the button shows the steps.
  let ask = null;
  addEventListener('beforeinstallprompt', e => { e.preventDefault(); ask = e; });
  addEventListener('appinstalled', () => { btn.remove(); dot.remove(); });

  // icons shown on their own get a spoken name; those next to their word are hidden from screen readers
  const svg = (d, name) => `<svg class="hs-i" viewBox="0 0 24 24" ${name ? `role="img" aria-label="${name}"` : 'aria-hidden="true"'}>${d}</svg>`;
  const I = {
    add: svg('<rect x="3.5" y="3.5" width="17" height="17" rx="4" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 8v8M8 12h8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'),
    share: svg('<path d="M12 3.5v11M8.2 7.2 12 3.4l3.8 3.8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M8.5 10.5H6.8a1.8 1.8 0 0 0-1.8 1.8v6.4a1.8 1.8 0 0 0 1.8 1.8h10.4a1.8 1.8 0 0 0 1.8-1.8v-6.4a1.8 1.8 0 0 0-1.8-1.8h-1.7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'),
    more: svg('<circle cx="5.5" cy="12" r="1.9" fill="currentColor"/><circle cx="12" cy="12" r="1.9" fill="currentColor"/><circle cx="18.5" cy="12" r="1.9" fill="currentColor"/>', 'the three-dot button'),
    dots: svg('<circle cx="12" cy="5.5" r="1.9" fill="currentColor"/><circle cx="12" cy="12" r="1.9" fill="currentColor"/><circle cx="12" cy="18.5" r="1.9" fill="currentColor"/>', 'the three-dot menu'),
    menu: svg('<path d="M5 7h14M5 12h14M5 17h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>', 'the three-line menu'),
  };
  I.shareAlone = I.share.replace('aria-hidden="true"', 'role="img" aria-label="the Share button"');
  const b = (t, i = '') => `<b>${i}${t}</b>`;
  const ADD = `${b('Add to Home Screen', I.add)}`, WEBAPP = `Keep ${b('Open as Web App')} on, and tap ${b('Add')}.`;
  // From Apple's and Google's help pages (checked Nov 2026: iOS 26 and 27, iPadOS 26 and 27, Chrome for iOS).
  const STEPS = {
    safari: ipad
      ? (safariV >= 26 ? [`Tap ${b('Share', I.share)} at the top of Safari, then ${b(safariV >= 27 ? 'View More' : 'More')}.`, `Tap ${ADD}.`, WEBAPP]
                       : [`Tap ${b('Share', I.share)} at the top of Safari.`, `Scroll down and tap ${ADD}.`, `Tap ${b('Add')}.`])
      : (safariV >= 26 ? [`Tap ${safariV >= 27 ? b('Page Menu') : `${b('', I.more)} (More)`} to the right of the address bar, then ${b('Share', I.share)}. If Safari shows ${b('', I.shareAlone)} at the bottom, tap that instead.`,
                          `Scroll down and tap ${ADD}. Tap ${b('View More')} first if you don't see it.`, WEBAPP]
                       : [`Tap ${b('Share', I.share)} at the bottom of Safari.`, `Scroll down and tap ${ADD}.`, `Tap ${b('Add')}.`]),
    chrome: [`Tap ${b('Share', I.share)} on the right of the address bar.`, `Scroll down and tap ${ADD}.`, `Tap ${b('Add')}.`],
    edge: [`Tap ${b('', I.menu)} (Edge's menu), then ${b('Share', I.share)}.`, `Tap ${ADD}.`, `Tap ${b('Add')}.`],
    firefox: [`Tap ${b('Share', I.share)}, or Firefox's menu and then Share.`, `Tap ${ADD}.`, `Tap ${b('Add')}.`],
    other: [`Tap your browser's ${b('Share', I.share)} button.`, `Tap ${ADD}.`, `Tap ${b('Add')}.`],
    inapp: [`This app's own browser can't add pages to the Home Screen. Open its menu (often ${b('', ios ? I.more : I.dots)}) and tap ${b(ios ? 'Open in Safari' : 'Open in Chrome')} or ${b('Open in browser')}.`,
            `In ${ios ? 'Safari' : 'your browser'}, tap ${ADD} at the top of this page again for the steps.`],
    android: [`Open your browser's menu: ${b('', I.dots)} at the top right in Chrome, ${b('', I.menu)} at the bottom in Samsung Internet.`,
              `Tap ${b('Add to Home screen')} or ${b('Install app')} (Samsung Internet: ${b('Add page to')}, then ${b('Home screen')}).`,
              `Tap ${b('Install')} or ${b('Add')}.`],
  };

  const css = document.createElement('style');
  css.textContent = `
  .hs-btn{all:unset;cursor:pointer;display:inline-flex;align-items:baseline;gap:5px;font:inherit;letter-spacing:inherit;text-transform:inherit;
          color:inherit;text-decoration:underline;text-underline-offset:auto;white-space:nowrap;-webkit-tap-highlight-color:transparent}
  .hs-btn:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:2px}
  .hs-btn .hs-i{display:block;width:15px;height:15px;flex:none;align-self:center}
  /* a phone: the date and the button share the line under the site names; the button wraps under the date when they don't fit */
  @media (max-width:560px){
    .mast .hs-row{grid-column:1/-1;grid-row:2;display:flex;flex-wrap:wrap;align-items:center;gap:4px 16px}
    .mast .hs-row .hs-btn{margin-left:auto}
  }
  .hs-sheet{border:0;padding:0;margin:auto auto 0;width:100%;max-width:440px;max-height:calc(100dvh - 24px);overflow:auto;
            background:var(--surface);color:var(--ink);border-radius:16px 16px 0 0;box-shadow:0 -8px 32px rgba(0,0,0,.22);
            font:16px/1.5 "Barlow",system-ui,-apple-system,sans-serif}
  @media (min-width:561px){ .hs-sheet{margin:auto;border-radius:16px} }
  .hs-sheet::backdrop{background:rgba(10,10,8,.45)}
  .hs-in{padding:20px 20px calc(20px + env(safe-area-inset-bottom))}
  .hs-top{display:flex;gap:14px;align-items:center}
  .hs-top img{width:56px;height:56px;border-radius:13px;flex:none;box-shadow:0 1px 3px rgba(0,0,0,.2)}
  .hs-sheet h2{font:700 24px/1.05 "Barlow Condensed","Barlow",system-ui,sans-serif;margin:0;outline:none}
  .hs-sheet .hs-sub{margin:4px 0 0;font-size:15px;color:var(--ink-2)}
  .hs-sheet ol{margin:16px 0 0;padding:0 0 0 24px}
  .hs-sheet li{margin:0 0 10px;padding-left:2px}
  .hs-sheet li b{font-weight:600;white-space:nowrap}
  .hs-sheet li .hs-i{display:inline-block;width:20px;height:20px;vertical-align:-4px;margin:0 2px;color:var(--accent-ink)}
  .hs-close{all:unset;box-sizing:border-box;cursor:pointer;display:block;width:100%;text-align:center;margin:12px 0 0;padding:11px;
            border-radius:10px;background:var(--well);font:600 16px "Barlow",system-ui,sans-serif;color:var(--ink)}
  .hs-close:focus-visible{outline:2px solid var(--accent);outline-offset:2px}`;
  document.head.append(css);

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'hs-btn';
  btn.setAttribute('aria-haspopup', 'dialog');
  btn.innerHTML = `${I.add}Add to Home Screen`;
  // "Updated …  ·  Add to Home Screen  ·  About": the button goes right after the date, in a row with it
  const row = document.createElement('span'), dot = document.createElement('span');
  row.className = 'hs-row';
  dot.className = 'dot';
  dot.textContent = ' · ';
  const date = [...mast.children].find(e => e.tagName === 'SPAN' && !e.classList.contains('dot'));
  if (date) { date.replaceWith(row); row.append(date, dot, btn); } else { mast.prepend(row); row.append(btn, dot); }

  let sheet;
  btn.addEventListener('click', async () => {
    if (ask) {                                  // Android: the browser's own install dialog, which works once per offer
      const e = ask;
      ask = null;
      e.prompt();
      const { outcome } = await e.userChoice;
      if (outcome === 'accepted') { btn.remove(); dot.remove(); }
      return;
    }
    if (!sheet) {
      const icon = document.querySelector('link[rel="apple-touch-icon"]')?.href;
      sheet = document.createElement('dialog');
      sheet.className = 'hs-sheet';
      sheet.setAttribute('aria-labelledby', 'hs-title');
      sheet.innerHTML = `<div class="hs-in"><div class="hs-top">${icon ? `<img src="${icon}" alt="">` : ''}<div>
        <h2 id="hs-title" tabindex="-1" autofocus>Add ${app} to your Home Screen</h2>
        <p class="hs-sub">It then opens from its own icon, like an app.</p></div></div>
        <ol>${STEPS[browser].map(s => `<li>${s}</li>`).join('')}</ol>
        <button type="button" class="hs-close">Close</button></div>`;
      sheet.querySelector('.hs-close').addEventListener('click', () => sheet.close());
      sheet.addEventListener('click', e => { if (e.target === sheet) sheet.close(); });   // a tap on the dimmed page
      document.body.append(sheet);
    }
    sheet.showModal();
    sheet.scrollTop = 0;
  });
})();
