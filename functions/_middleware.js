// Cloudflare Pages Function — figteam 통합 대시보드
// 화면(public/)은 Pages가 제공하고, 백엔드 경로만 온프렘 터널(BACKEND_ORIGIN)로 전달한다.
// 같은 출처(figteam.ktci5.kr)를 유지하므로 로그인 쿠키가 그대로 동작한다.
//
// 환경변수 (Pages > Settings > Variables)
//   BACKEND_ORIGIN          예: https://figteam-api.ktci5.kr  (minwon-tunnel → localhost:18088)
//   CF_ACCESS_CLIENT_ID     선택: 백엔드 호스트명을 Cloudflare Access 서비스 토큰으로 막았을 때
//   CF_ACCESS_CLIENT_SECRET 선택

const BACKEND_PATH = /^\/(api|sso)\//;

function backendHeaders(request, env) {
  const h = new Headers(request.headers);
  h.delete('host');
  if (env.CF_ACCESS_CLIENT_ID && env.CF_ACCESS_CLIENT_SECRET) {
    h.set('CF-Access-Client-Id', env.CF_ACCESS_CLIENT_ID);
    h.set('CF-Access-Client-Secret', env.CF_ACCESS_CLIENT_SECRET);
  }
  return h;
}

async function renderGatewayError(env, request, message, code = 503) {
  if (env.ASSETS) {
    try {
      const pageRes = await env.ASSETS.fetch(new URL('/503.html', request.url));
      if (pageRes.status === 200) {
        return new Response(pageRes.body, {
          status: code,
          headers: {
            'Content-Type': 'text/html; charset=utf-8',
            'Cache-Control': 'no-store'
          }
        });
      }
    } catch (_) {}
  }
  return new Response(`503 Service Unavailable: ${message || '온프렘 백엔드 연결 불가'}`, {
    status: code,
    headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' }
  });
}

async function render404(env, request) {
  if (env.ASSETS) {
    try {
      const pageRes = await env.ASSETS.fetch(new URL('/404.html', request.url));
      if (pageRes.status === 200) {
        return new Response(pageRes.body, {
          status: 404,
          headers: {
            'Content-Type': 'text/html; charset=utf-8',
            'Cache-Control': 'no-store'
          }
        });
      }
    } catch (_) {}
  }
  return new Response('404 Not Found: 요청하신 도면(페이지)을 찾을 수 없습니다.', {
    status: 404,
    headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' }
  });
}

async function toBackend(request, url, env) {
  const origin = env.BACKEND_ORIGIN.replace(/\/+$/, '');
  const init = { method: request.method, headers: backendHeaders(request, env), redirect: 'manual' };
  if (request.method !== 'GET' && request.method !== 'HEAD') init.body = await request.arrayBuffer();

  const isHtml = request.headers.get('accept')?.includes('text/html');

  try {
    const res = await fetch(origin + url.pathname + url.search, init);
    // 백엔드 게이트웨이 에러(502/503/504) 시 HTML 요청이면 커스텀 503 페이지 제공
    if (res.status >= 502 && res.status <= 504) {
      if (isHtml) {
        return await renderGatewayError(env, request, `백엔드 상태 코드 ${res.status}`);
      }
    }
    const out = new Response(res.body, res);
    const loc = out.headers.get('Location');
    if (loc && loc.startsWith(origin)) out.headers.set('Location', loc.slice(origin.length) || '/');
    out.headers.set('Cache-Control', 'no-store');
    return out;
  } catch (err) {
    if (isHtml) {
      return await renderGatewayError(env, request, `온프렘 터널 연결 실패 (${err.message})`);
    }
    return new Response(JSON.stringify({
      error: 'Service Unavailable',
      message: '온프렘 백엔드 또는 터널 데몬에 연결할 수 없습니다.',
      detail: String(err)
    }), {
      status: 503,
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }
    });
  }
}

async function checkSession(request, env) {
  const cookie = request.headers.get('Cookie') || '';
  if (!cookie.includes('figteam_session=')) return { ok: false, error: null };
  const origin = env.BACKEND_ORIGIN.replace(/\/+$/, '');
  const h = backendHeaders(request, env);
  try {
    const res = await fetch(origin + '/api/session', { headers: h, redirect: 'manual' });
    return { ok: res.status === 200, error: null };
  } catch (e) {
    return { ok: false, error: e };
  }
}

export async function onRequest(context) {
  const { request, env, next } = context;
  if (!env.BACKEND_ORIGIN) {
    return new Response('BACKEND_ORIGIN 환경변수가 없습니다. Pages 설정에서 백엔드 터널 주소를 지정하세요.', { status: 500 });
  }
  const url = new URL(request.url);
  const p = url.pathname;

  // 1. 에러 페이지 직접 접근은 바로 서빙
  if (p === '/404' || p === '/404.html') return render404(env, request);
  if (p === '/502' || p === '/502.html' || p === '/503' || p === '/503.html') return renderGatewayError(env, request, '시스템 점검 및 복구 안내', 200);

  // 2. 백엔드 API/SSO 및 로그인 POST 처리
  if (BACKEND_PATH.test(p) || p === '/logout' || (p === '/login' && request.method === 'POST')) {
    return toBackend(request, url, env);
  }

  // 3. 로그인 화면은 공개
  if (p === '/login' || p === '/login.html') return next();

  // 4. 정적 자산(theme, js, css, 이미지 등 확장자가 있는 파일)
  if (/\.[a-zA-Z0-9]+$/.test(p) && p !== '/index.html') {
    const res = await next();
    if (res.status === 404) return render404(env, request);
    return res;
  }

  // 5. 메인 포털 경로(/, /index, /index.html)인 경우 세션 확인
  if (p === '/' || p === '/index' || p === '/index.html') {
    const session = await checkSession(request, env);
    if (!session.ok) {
      // 만약 백엔드 연결 자체가 터널 다운으로 실패한 경우 503 안내
      if (session.error) {
        return renderGatewayError(env, request, '온프렘 백엔드 연결 실패로 세션을 확인할 수 없습니다.');
      }
      return Response.redirect(new URL('/login', url).toString(), 302);
    }
    const res = await next();
    const out = new Response(res.body, res);
    out.headers.set('Cache-Control', 'no-store');
    return out;
  }

  // 6. 그 외 정의되지 않은 모든 경로는 404 페이지로 안내
  const res = await next();
  if (res.status === 404) {
    return render404(env, request);
  }
  return res;
}
