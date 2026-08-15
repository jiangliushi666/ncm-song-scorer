/** 把官网匿名 128k 播放地址转给 GitHub Pages（接口本身没有 CORS）。不做 VIP 解锁。 */

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

function cors() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Cache-Control": "no-store",
  };
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...cors(), "Content-Type": "application/json; charset=utf-8" },
  });
}

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors() });
    }
    const id = new URL(request.url).searchParams.get("id") || "";
    if (!/^\d{1,20}$/.test(id)) {
      return json({ error: "bad id" }, 400);
    }
    const api =
      "https://music.163.com/api/song/enhance/player/url?id=" +
      id +
      "&ids=[" +
      id +
      "]&br=128000";
    const resp = await fetch(api, {
      headers: {
        "User-Agent": UA,
        Referer: "https://music.163.com",
        Cookie: "os=pc; appver=8.10.35",
      },
    });
    if (!resp.ok) {
      return json({ id: Number(id), url: null, error: "upstream " + resp.status }, 502);
    }
    const data = await resp.json();
    const item = (data.data && data.data[0]) || {};
    let url = item.url || null;
    if (url && url.indexOf("http://") === 0) {
      url = "https://" + url.slice(7);
    }
    return json({
      id: Number(id),
      url,
      br: item.br || null,
      fee: item.fee == null ? null : item.fee,
    });
  },
};
