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

async function toBackend(request, url, env) {
  const origin = env.BACKEND_ORIGIN.replace(/\/+$/, '');
  const init = { method: request.method, headers: backendHeaders(request, env), redirect: 'manual' };
  if (request.method !== 'GET' && request.method !== 'HEAD') init.body = await request.arrayBuffer();
  const res = await fetch(origin + url.pathname + url.search, init);
  const out = new Response(res.body, res);
  const loc = out.headers.get('Location');
  if (loc && loc.startsWith(origin)) out.headers.set('Location', loc.slice(origin.length) || '/');
  out.headers.set('Cache-Control', 'no-store');
  return out;
}

async function hasSession(request, env) {
  const cookie = request.headers.get('Cookie') || '';
  if (!cookie.includes('figteam_session=')) return false;
  const origin = env.BACKEND_ORIGIN.replace(/\/+$/, '');
  const h = backendHeaders(request, env);
  try {
    const res = await fetch(origin + '/api/session', { headers: h, redirect: 'manual' });
    return res.status === 200;
  } catch (e) {
    return false;
  }
}

export async function onRequest(context) {
  const { request, env, next } = context;
  if (!env.BACKEND_ORIGIN) {
    return new Response('BACKEND_ORIGIN 환경변수가 없습니다. Pages 설정에서 백엔드 터널 주소를 지정하세요.', { status: 500 });
  }
  const url = new URL(request.url);
  const p = url.pathname;

  if (BACKEND_PATH.test(p) || p === '/logout' || (p === '/login' && request.method === 'POST')) {
    return toBackend(request, url, env);
  }
  // 로그인 화면만 공개, 그 외 정적 경로(/, /index, /index.html 등)는 세션 확인 후 제공
  if (p === '/login' || p === '/login.html') return next();
  if (!(await hasSession(request, env))) return Response.redirect(new URL('/login', url).toString(), 302);
  const res = await next();
  const out = new Response(res.body, res);
  out.headers.set('Cache-Control', 'no-store');
  return out;
}
