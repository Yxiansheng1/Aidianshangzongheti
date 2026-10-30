"""替换写作台的发布区：按平台分组，账号下拉跟着平台走。"""
import re
from pathlib import Path

PATH = Path(r"D:\AIdianshangzongheti\pipeline\gui\ui.html")
text = PATH.read_text(encoding="utf-8")

start = text.find('    var plat = draft.platform || "小红书";')
end = text.find('    h += \'<div id="w-extra" style="margin-top:14px"></div>\';')
if start < 0 or end < 0:
    raise SystemExit("定位失败")

NEW = '''    var plat = draft.platform || "小红书";
    var notePubs = platformsWith("note");
    notePubs.sort(function(a, b){ return (b === plat) - (a === plat); });

    // ---- 发布区：按平台分组，平台名是标题，账号下拉在平台下面 ----
    h += '<div style="margin-top:18px;border-top:1px solid var(--line);padding-top:14px">';
    h += '<div class="muted" style="font-weight:600;margin-bottom:8px">发到哪里</div>';

    function accSelect(p){
      var accs = accountsFor(p);
      if(accs.length > 1){
        return '<select data-acc-for="' + esc(p) + '" style="width:155px">' +
          accs.map(function(a){
            return '<option value="' + esc(a.name) + '">' + esc(a.label) +
              (a.logged ? "" : "（未登录）") + '</option>';
          }).join("") + '</select>';
      }
      if(accs.length === 1){
        return '<span class="muted" style="font-size:12px">' + esc(accs[0].label) +
          (accs[0].logged ? "" : "（未登录）") + '</span>';
      }
      return '';
    }

    notePubs.forEach(function(p){
      var isHeadline = (p === "头条");
      h += '<div style="margin-bottom:10px;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:#fcfbf9">';
      h += '<div class="row" style="gap:8px;flex-wrap:wrap;align-items:center">';
      h += '<b style="font-size:13.5px">' + esc(p) + '</b>';
      h += accSelect(p);
      if(isHeadline){
        h += '<button class="btn" data-w="headline" data-platform="' + esc(p) + '">填进编辑器</button>' +
             '<button class="btn" data-w="both" data-platform="' + esc(p) + '">一稿两版</button>' +
             '<button class="btn small" data-w="login" data-platform="' + esc(p) + '">登录这个号</button>';
      }else{
        h += '<button class="btn" data-w="pub" data-platform="' + esc(p) + '">发布</button>' +
             '<button class="btn small" data-w="cmd" data-platform="' + esc(p) + '">看命令</button>';
      }
      h += '</div>';
      if(isHeadline){
        h += '<div class="muted" style="font-size:11.5px;margin-top:6px">' +
             '头条没有发布接口：工具把稿子填进编辑器，最后点「发布」由你自己按。</div>';
      }
      h += '</div>';
    });

    var vo = platformsWith("video").filter(function(p){ return notePubs.indexOf(p) < 0; });
    if(vo.length){
      h += '<div class="muted" style="font-size:12px;margin-top:4px">' +
           '只能发视频：' + vo.map(esc).join("、") + '（上面点「生成视频」，拼完这里会出现按钮）</div>';
    }
    var noPub = (writerMeta || {}).no_publish || {};
    Object.keys(noPub).forEach(function(k){
      h += '<div class="muted" style="font-size:12px;margin-top:4px">' + esc(k) + '：' + esc(noPub[k]) + '</div>';
    });

    h += '<div class="row" style="margin-top:12px;gap:8px;flex-wrap:wrap">';
    if((d.images || []).length){
      h += '<button class="btn" data-w="video">' + (d.videoPath ? "重新拼视频" : "生成视频") + '</button>';
    }
    h += '</div>';
    h += '</div>';

    if(d.videoPath){
      var vi = d.videoInfo || {};
      h += '<div style="margin-top:12px"><div class="muted" style="font-weight:600;margin-bottom:6px">视频（发视频的平台用这个）' +
        (vi.duration ? '\\u3000' + vi.duration + ' 秒\\u3000' + vi.width + '\\u00d7' + vi.height + '\\u3000' + vi.size_mb + ' MB' : '') + '</div>' +
        '<video controls src="' + d.videoUrl + '" style="max-width:280px;border-radius:8px;border:1px solid var(--line)"></video></div>' +
        '<div class="row" style="margin-top:10px;gap:8px;flex-wrap:wrap">' +
        platformsWith("video").filter(function(p){ return notePubs.indexOf(p) < 0; }).map(function(p){
          return '<div style="border:1px solid var(--line);border-radius:8px;padding:8px 10px;background:#fcfbf9">' +
            '<div class="row" style="gap:6px;align-items:center">' +
            '<b style="font-size:12.5px">' + esc(p) + '</b>' + accSelect(p) +
            '<button class="btn small" data-w="pub" data-platform="' + esc(p) + '">发布</button>' +
            '</div></div>';
        }).join("") + '</div>';
    }

'''

PATH.write_text(text[:start] + NEW + text[end:], encoding="utf-8")
print("替换完成")
