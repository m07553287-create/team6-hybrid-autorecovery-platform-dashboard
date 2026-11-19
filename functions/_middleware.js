// Cloudflare Pages Function — figteam 통합 대시보드
// 화면(public/)은 Pages가 제공하고, 백엔드 경로만 온프렘 터널(BACKEND_ORIGIN)로 전달한다.
// 같은 출처(figteam.ktci5.kr)를 유지하므로 로그인 쿠키가 그대로 동작한다.
//
// 환경변수 (Pages > Settings > Variables)
//   BACKEND_ORIGIN          예: https://figteam-api.ktci5.kr  (minwon-tunnel → localhost:18088)
//   CF_ACCESS_CLIENT_ID     선택: 백엔드 호스트명을 Cloudflare Access 서비스 토큰으로 막았을 때
//   CF_ACCESS_CLIENT_SECRET 선택

const BACKEND_PATH = /^\/(api|sso)\/|^\/term$/;   // /term = 통합 터미널(백엔드가 로그인 확인 후 제공)

function backendHeaders(request, env) {
  const h = new Headers(request.headers);
  h.delete('host');
  if (env.CF_ACCESS_CLIENT_ID && env.CF_ACCESS_CLIENT_SECRET) {
    h.set('CF-Access-Client-Id', env.CF_ACCESS_CLIENT_ID);
    h.set('CF-Access-Client-Secret', env.CF_ACCESS_CLIENT_SECRET);
  }
  return h;
}

// 백엔드 및 온프렘 클라우드 인프라 생존 여부 점검 (타임아웃 2.5초)
async function isBackendAlive(env) {
  if (!env.BACKEND_ORIGIN) return false;
  const origin = env.BACKEND_ORIGIN.replace(/\/+$/, '');
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);
    const res = await fetch(origin + '/api/session', {
      method: 'GET',
      headers: backendHeaders({ headers: new Headers() }, env),
      redirect: 'manual',
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    // 200(인증유효), 401(미인증이지만 백엔드 생존) 등 500 미만 코드는 정상 가동
    return res.status < 500;
  } catch (_) {
    return false; // 연결 거부, 터널 중단, 전원 OFF
  }
}

async function renderOffline(env, request) {
  if (env.ASSETS) {
    try {
      const pageRes = await env.ASSETS.fetch(new URL('/offline.html', request.url));
      if (pageRes.status === 200) {
        return new Response(pageRes.body, {
          status: 503,
          headers: {
            'Content-Type': 'text/html; charset=utf-8',
            'Cache-Control': 'no-store'
          }
        });
      }
    } catch (_) {}
  }
  return renderGatewayError(env, request, '모든 클라우드 인프라 OFF (시스템 절전/대기 모드)', 503);
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
    // 백엔드 게이트웨이 에러(502/503/504) 시 HTML 요청이면 커스텀 오프라인 페이지 제공
    if (res.status >= 502 && res.status <= 504) {
      if (isHtml) {
        return await renderOffline(env, request);
      }
    }
    const out = new Response(res.body, res);
    const loc = out.headers.get('Location');
    if (loc && loc.startsWith(origin)) out.headers.set('Location', loc.slice(origin.length) || '/');
    out.headers.set('Cache-Control', 'no-store');
    return out;
  } catch (err) {
    if (isHtml) {
      return await renderOffline(env, request);
    }
    return new Response(JSON.stringify({
      error: 'Service Unavailable',
      message: '모든 클라우드가 OFF 상태이거나 백엔드 터널에 연결할 수 없습니다.',
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

  // 1. 에러 및 오프라인 상태 페이지 직접 접근은 바로 서빙
  if (p === '/404' || p === '/404.html') return render404(env, request);
  if (p === '/502' || p === '/502.html' || p === '/503' || p === '/503.html') return renderGatewayError(env, request, '시스템 점검 및 복구 안내', 200);
  if (p === '/offline' || p === '/offline.html') return renderOffline(env, request);

  // 2. 정적 자산(theme, js, css, 이미지 등 확장자가 있는 파일)
  if (/\.[a-zA-Z0-9]+$/.test(p) && p !== '/index.html' && p !== '/login.html') {
    const res = await next();
    if (res.status === 404) return render404(env, request);
    return res;
  }

  // 3. 백엔드 연결 여부 점검 (모든 클라우드가 OFF인지 확인)
  const backendAlive = await isBackendAlive(env);

  // [중요] 모든 클라우드가 OFF(백엔드 연결 불가)인 경우:
  // 로그인 콘솔 대신 "모든 클라우드 OFF" 상태 화면을 표시하여 로그인 이벤트를 사전에 원천 차단!
  if (!backendAlive) {
    // API 호출인 경우 JSON 안내 반환
    if (BACKEND_PATH.test(p)) {
      return new Response(JSON.stringify({
        error: 'ALL_CLOUDS_OFF',
        message: '모든 클라우드가 OFF 상태입니다. 인프라 가동 후 다시 시도하십시오.'
      }), {
        status: 503,
        headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }
      });
    }
    // 브라우저 화면 접근(메인 /, /login, /index 등)은 모두 오프라인 안내 화면 서빙
    return renderOffline(env, request);
  }

  // 4. 백엔드가 살아있는 상태: 백엔드 API/SSO 및 로그인 POST 처리
  if (BACKEND_PATH.test(p) || p === '/logout' || (p === '/login' && request.method === 'POST')) {
    return toBackend(request, url, env);
  }

  // 5. 로그인 화면 접근 (백엔드 정상 가동 시 로그인 허용)
  if (p === '/login' || p === '/login.html') return next();

  // 6. 메인 포털 경로(/, /index, /index.html)인 경우 세션 확인
  if (p === '/' || p === '/index' || p === '/index.html') {
    const session = await checkSession(request, env);
    if (!session.ok) {
      if (session.error) {
        return renderOffline(env, request);
      }
      return Response.redirect(new URL('/login', url).toString(), 302);
    }
    const res = await next();
    const out = new Response(res.body, res);
    out.headers.set('Cache-Control', 'no-store');
    return out;
  }

  // 7. 그 외 정의되지 않은 모든 경로는 404 페이지로 안내
  const res = await next();
  if (res.status === 404) {
    return render404(env, request);
  }
  return res;
}
