package com.rober.trenes;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONArray;
import org.json.JSONObject;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

import javax.xml.parsers.DocumentBuilderFactory;

public class MainActivity extends Activity {
    private WebView web;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(Color.parseColor("#0a0e17"));
        getWindow().setNavigationBarColor(Color.parseColor("#0a0e17"));
        getWindow().getDecorView().setSystemUiVisibility(0);

        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0a0e17"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                abrirFuera(request.getUrl());
                return true;
            }
        });
        web.addJavascriptInterface(new Feeds(), "Android");
        setContentView(web);
        web.loadUrl("file:///android_asset/index.html");
    }

    private void abrirFuera(Uri uri) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException ignored) {
        }
    }

    // Renfe no envía CORS: se descarga aquí y se pasa al mapa. Además se
    // normalizan FGC (protobuf GTFS-RT) y Metro Bilbao (XML SIRI).
    private class Feeds {
        @JavascriptInterface
        public String getData() {
            String cercanias = descargar("https://gtfsrt.renfe.com/vehicle_positions.json");
            String ld = descargar("https://tiempo-real.largorecorrido.renfe.com/renfe-visor/flotaLD.json");
            String updates = descargar("https://gtfsrt.renfe.com/trip_updates.json");
            String otros = otros();
            return "{\"cercanias\":" + (cercanias == null ? "null" : cercanias)
                 + ",\"ld\":" + (ld == null ? "null" : ld)
                 + ",\"updates\":" + (updates == null ? "null" : updates)
                 + ",\"otros\":" + otros + "}";
        }

        @JavascriptInterface
        public String getFoto(String consulta) {
            try {
                String url = "https://es.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch="
                        + URLEncoder.encode(consulta, "UTF-8")
                        + "&gsrlimit=1&prop=pageimages&piprop=thumbnail&pithumbsize=500"
                        + "&format=json&formatversion=2";
                String json = descargar(url);
                if (json == null) return "";
                JSONObject query = new JSONObject(json).optJSONObject("query");
                if (query == null) return "";
                JSONArray pages = query.optJSONArray("pages");
                if (pages == null || pages.length() == 0) return "";
                JSONObject page = pages.getJSONObject(0);
                JSONObject thumb = page.optJSONObject("thumbnail");
                if (thumb == null) return "";
                JSONObject res = new JSONObject();
                res.put("url", thumb.optString("source", ""));
                res.put("pagina", page.optString("title", ""));
                return res.toString();
            } catch (Exception e) {
                return "";
            }
        }

        private String otros() {
            JSONArray arr = new JSONArray();
            try { fgc(arr); } catch (Exception ignored) { }
            try { metroBilbao(arr); } catch (Exception ignored) { }
            return arr.toString();
        }

        private void fgc(JSONArray arr) throws Exception {
            String meta = descargar("https://dadesobertes.fgc.cat/api/explore/v2.1/catalog/datasets/"
                    + "vehicle-positions-gtfs_realtime/records?limit=1");
            if (meta == null) return;
            JSONArray results = new JSONObject(meta).optJSONArray("results");
            if (results == null || results.length() == 0) return;
            JSONObject file = results.getJSONObject(0).optJSONObject("file");
            if (file == null) return;
            String url = file.optString("url", "");
            if (url.length() == 0) return;
            byte[] pb = descargarBytes(url, 6000, 9000);
            if (pb != null) parseFeed(pb, arr);
        }

        private void metroBilbao(JSONArray arr) throws Exception {
            byte[] xml = descargarBytes(
                    "https://ctb-siri.s3.eu-south-2.amazonaws.com/metro-bilbao-vehicle-positions.xml",
                    6000, 9000);
            if (xml == null) return;
            DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
            dbf.setNamespaceAware(false);
            try {
                dbf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            } catch (Exception ignored) { }
            Document doc = dbf.newDocumentBuilder().parse(new ByteArrayInputStream(xml));
            NodeList acts = doc.getElementsByTagName("VehicleActivity");
            for (int i = 0; i < acts.getLength(); i++) {
                Element act = (Element) acts.item(i);
                NodeList locs = act.getElementsByTagName("VehicleLocation");
                if (locs.getLength() == 0) continue;
                Element loc = (Element) locs.item(0);
                double lat = numero(texto(loc, "Latitude"));
                double lon = numero(texto(loc, "Longitude"));
                if (Double.isNaN(lat) || Double.isNaN(lon)) continue;
                JSONObject o = new JSONObject();
                o.put("op", "Metro Bilbao");
                o.put("line", texto(act, "LineRef"));
                o.put("dest", texto(act, "DestinationRef"));
                o.put("veh", texto(act, "VehicleRef"));
                o.put("trip", texto(act, "VehicleJourneyRef"));
                o.put("time", texto(act, "RecordedAtTime"));
                o.put("lat", lat);
                o.put("lon", lon);
                arr.put(o);
            }
        }

        private String texto(Element padre, String tag) {
            NodeList nl = padre.getElementsByTagName(tag);
            return nl.getLength() > 0 ? nl.item(0).getTextContent().trim() : "";
        }

        private double numero(String s) {
            try { return Double.parseDouble(s); } catch (Exception e) { return Double.NaN; }
        }

        // --- GTFS-RT protobuf (FGC) ---
        private void parseFeed(byte[] b, JSONArray arr) {
            int[] p = {0};
            while (p[0] < b.length) {
                long key = varint(b, p);
                int field = (int) (key >>> 3);
                int wire = (int) (key & 7);
                if (field == 2 && wire == 2) {
                    try { parseEntity(bytes(b, p), arr); } catch (Exception ignored) { }
                } else {
                    skip(b, p, wire);
                }
            }
        }

        private void parseEntity(byte[] b, JSONArray arr) {
            int[] p = {0};
            while (p[0] < b.length) {
                long key = varint(b, p);
                int field = (int) (key >>> 3);
                int wire = (int) (key & 7);
                if (field == 4 && wire == 2) {
                    JSONObject v = parseVehicle(bytes(b, p));
                    if (v != null) arr.put(v);
                } else {
                    skip(b, p, wire);
                }
            }
        }

        private JSONObject parseVehicle(byte[] b) {
            double lat = Double.NaN, lon = Double.NaN;
            float speed = -1f;
            String trip = "", route = "", vid = "", label = "";
            long ts = 0;
            int[] p = {0};
            while (p[0] < b.length) {
                long key = varint(b, p);
                int field = (int) (key >>> 3);
                int wire = (int) (key & 7);
                if (field == 1 && wire == 2) {
                    byte[] t = bytes(b, p);
                    int[] q = {0};
                    while (q[0] < t.length) {
                        long k2 = varint(t, q);
                        int f2 = (int) (k2 >>> 3);
                        int w2 = (int) (k2 & 7);
                        if (f2 == 1 && w2 == 2) trip = str(t, q);
                        else if (f2 == 5 && w2 == 2) route = str(t, q);
                        else skip(t, q, w2);
                    }
                } else if (field == 2 && wire == 2) {
                    byte[] pos = bytes(b, p);
                    int[] q = {0};
                    while (q[0] < pos.length) {
                        long k2 = varint(pos, q);
                        int f2 = (int) (k2 >>> 3);
                        int w2 = (int) (k2 & 7);
                        if (f2 == 1 && w2 == 5) lat = Float.intBitsToFloat(fixed32(pos, q));
                        else if (f2 == 2 && w2 == 5) lon = Float.intBitsToFloat(fixed32(pos, q));
                        else if (f2 == 5 && w2 == 5) speed = Float.intBitsToFloat(fixed32(pos, q));
                        else skip(pos, q, w2);
                    }
                } else if (field == 5 && wire == 0) {
                    ts = varint(b, p);
                } else if (field == 8 && wire == 2) {
                    byte[] vd = bytes(b, p);
                    int[] q = {0};
                    while (q[0] < vd.length) {
                        long k2 = varint(vd, q);
                        int f2 = (int) (k2 >>> 3);
                        int w2 = (int) (k2 & 7);
                        if (f2 == 1 && w2 == 2) vid = str(vd, q);
                        else if (f2 == 2 && w2 == 2) label = str(vd, q);
                        else skip(vd, q, w2);
                    }
                } else {
                    skip(b, p, wire);
                }
            }
            if (Double.isNaN(lat) || Double.isNaN(lon)) return null;
            try {
                JSONObject o = new JSONObject();
                o.put("op", "FGC");
                o.put("line", route);
                o.put("trip", trip);
                o.put("veh", label.length() > 0 ? label : vid);
                o.put("time", ts);
                o.put("lat", lat);
                o.put("lon", lon);
                if (speed >= 0) o.put("speed", speed);
                return o;
            } catch (Exception e) {
                return null;
            }
        }

        private long varint(byte[] b, int[] p) {
            long r = 0;
            int s = 0;
            while (true) {
                int x = b[p[0]++] & 0xFF;
                r |= (long) (x & 0x7F) << s;
                if ((x & 0x80) == 0) return r;
                s += 7;
                if (s > 63) throw new RuntimeException("varint");
            }
        }

        private void skip(byte[] b, int[] p, int wire) {
            if (wire == 0) {
                varint(b, p);
            } else if (wire == 1) {
                p[0] += 8;
            } else if (wire == 2) {
                int len = (int) varint(b, p);
                p[0] += len;
            } else if (wire == 5) {
                p[0] += 4;
            } else {
                throw new RuntimeException("wire");
            }
            if (p[0] > b.length) throw new RuntimeException("truncado");
        }

        private byte[] bytes(byte[] b, int[] p) {
            int len = (int) varint(b, p);
            if (len < 0 || p[0] + len > b.length) throw new RuntimeException("len");
            byte[] out = new byte[len];
            System.arraycopy(b, p[0], out, 0, len);
            p[0] += len;
            return out;
        }

        private String str(byte[] b, int[] p) {
            byte[] out = bytes(b, p);
            try { return new String(out, "UTF-8"); } catch (Exception e) { return ""; }
        }

        private int fixed32(byte[] b, int[] p) {
            if (p[0] + 4 > b.length) throw new RuntimeException("fixed");
            int v = (b[p[0]] & 0xFF) | ((b[p[0] + 1] & 0xFF) << 8)
                    | ((b[p[0] + 2] & 0xFF) << 16) | ((b[p[0] + 3] & 0xFF) << 24);
            p[0] += 4;
            return v;
        }

        private String descargar(String url) {
            byte[] b = descargarBytes(url, 15000, 20000);
            if (b == null) return null;
            try { return new String(b, "UTF-8"); } catch (Exception e) { return null; }
        }

        private byte[] descargarBytes(String url, int connectMs, int readMs) {
            HttpURLConnection c = null;
            try {
                c = (HttpURLConnection) new URL(url).openConnection();
                c.setConnectTimeout(connectMs);
                c.setReadTimeout(readMs);
                c.setRequestProperty("Accept", "*/*");
                c.setRequestProperty("User-Agent", "TrenesEspana/1.0 (Android)");
                InputStream in = c.getInputStream();
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] buf = new byte[8192];
                int n;
                while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                in.close();
                return out.toByteArray();
            } catch (Exception e) {
                return null;
            } finally {
                if (c != null) c.disconnect();
            }
        }
    }
}
