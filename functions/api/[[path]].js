function buildUpstreamUrl(requestUrl, pathParam, apiOrigin) {
  const normalizedOrigin = apiOrigin.endsWith("/") ? apiOrigin : `${apiOrigin}/`;
  const pathSegments = Array.isArray(pathParam) ? pathParam : pathParam ? [pathParam] : [];
  const upstreamPath = pathSegments.length ? pathSegments.join("/") : "";
  const upstreamUrl = new URL(upstreamPath, normalizedOrigin);
  upstreamUrl.search = requestUrl.search;
  return upstreamUrl;
}

export async function onRequest(context) {
  const apiOrigin = context.env.API_ORIGIN;

  if (!apiOrigin) {
    return new Response(
      "Missing Cloudflare Pages environment variable API_ORIGIN for the /api proxy.",
      { status: 500 }
    );
  }

  const requestUrl = new URL(context.request.url);
  const upstreamUrl = buildUpstreamUrl(requestUrl, context.params.path, apiOrigin);
  const requestInit = {
    method: context.request.method,
    headers: context.request.headers,
    redirect: "follow",
  };

  if (!["GET", "HEAD"].includes(context.request.method)) {
    requestInit.body = context.request.body;
  }

  const upstreamRequest = new Request(upstreamUrl.toString(), requestInit);
  return fetch(upstreamRequest);
}
