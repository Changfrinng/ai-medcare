// Build: inline data/drugs.json into the app, emit artifact page + standalone PWA
const fs=require("fs"),path=require("path");
const root=__dirname;
const data=JSON.stringify(JSON.parse(fs.readFileSync(path.join(root,"data/drugs.json"),"utf8")));
const src=fs.readFileSync(path.join(root,"frontend/app.src.html"),"utf8").replace("/*__DRUGS__*/",()=>data);
fs.mkdirSync(path.join(root,"dist"),{recursive:true});
fs.writeFileSync(path.join(root,"dist/app.html"),src);
const pwa=`<!doctype html>\n<html lang="zh-Hant-TW">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n<link rel="manifest" href="manifest.webmanifest">\n<link rel="icon" href="icon.svg" type="image/svg+xml">\n<link rel="apple-touch-icon" href="icon.svg">\n<meta name="apple-mobile-web-app-capable" content="yes">\n<style>[hidden]{display:none!important}html,body{height:100%}img{max-width:100%}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}</style>\n</head>\n<body>\n${src}\n</body>\n</html>\n`;
fs.writeFileSync(path.join(root,"frontend/index.html"),pwa);
console.log("built",src.length,"bytes");
