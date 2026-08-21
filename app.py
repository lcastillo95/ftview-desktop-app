import html
import io
import math
import os
import re
import sqlite3
import sys
import threading
import xml.etree.ElementTree as ET
import webview


def get_app_data_path() -> str:
  if sys.platform == "win32":
    base_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
  else:
    base_dir = os.path.expanduser("~/.local/share")
  app_dir = os.path.join(base_dir, "HMITagFinder")
  os.makedirs(app_dir, exist_ok=True)
  return app_dir


class FlattenedFTViewCompiler:

  def __init__(
      self, xml_bytes: bytes, file_name: str, tag_overrides: dict = None
  ):
    self.file_name = file_name
    self.tree = ET.parse(io.BytesIO(xml_bytes))
    self.root = self.tree.getroot()
    self.tag_overrides = tag_overrides or {}

    settings = self.root.find(".//displaySettings")
    if settings is not None:
      self.width = int(settings.attrib.get("width", 1920))
      self.height = int(settings.attrib.get("height", 1080))
      self.bg_color = settings.attrib.get("backColor", "#EEE7D7")
    else:
      self.width = 1920
      self.height = 1080
      self.bg_color = "#EEE7D7"

  def _get_transform(self, elem) -> str:
    t = elem.find("./transform")
    if t is None:
      return ""
    a = t.attrib.get("scaleWidth", "1")
    b = t.attrib.get("shearHeight", "0")
    c = t.attrib.get("shearWidth", "0")
    d = t.attrib.get("scaleHeight", "1")
    e = t.attrib.get("offsetWidth", "0")
    f = t.attrib.get("offsetHeight", "0")
    return f'transform="matrix({a} {b} {c} {d} {e} {f})"'

  def _extract_local_tags(self, elem) -> list:
    info = []
    name = elem.attrib.get("name", "")
    if name:
      info.append(f"Name: {name}")

    tag_pattern = r"\{([A-Za-z0-9_#/@\.\:\[\]\-\s\$\%]+)\}"
    for k, v in elem.attrib.items():
      if isinstance(v, str):
        for tag_match in re.findall(tag_pattern, v):
          clean_t = tag_match.strip()
          if clean_t and not clean_t.isdigit():
            info.append(f"Tag: {clean_t}")

    for conn in elem.findall("./connections/connection"):
      expr = conn.attrib.get("expression") or conn.attrib.get("tag")
      conn_name = conn.attrib.get("name", "Value")
      if expr:
        info.append(f"Conn ({conn_name}): {expr}")

    for anim in elem.findall("./animations/*"):
      anim_type = anim.tag.replace("animate", "")
      expr = anim.attrib.get("expression") or anim.attrib.get("tag")
      rel = anim.attrib.get("releaseAction")
      prs = anim.attrib.get("pressAction")
      if expr:
        info.append(f"Anim ({anim_type}): {expr}")
      if rel:
        info.append(f"Release: {rel}")
      if prs:
        info.append(f"Press: {prs}")

    for act in elem.findall("./action"):
      t = act.attrib.get("tag")
      act_type = act.attrib.get("type", "Action")
      if t:
        info.append(f"Action ({act_type}): {t}")

    for cmd in elem.findall("./command"):
      rel = cmd.attrib.get("releaseAction")
      prs = cmd.attrib.get("pressAction")
      if rel:
        info.append(f"Cmd (Release): {rel}")
      if prs:
        info.append(f"Cmd (Press): {prs}")

    return info

  def _build_tag_attr(self, tag_list: list) -> str:
    if not tag_list:
      return ""
    unique = []
    for item in tag_list:
      if item not in unique:
        unique.append(item)
    escaped = html.escape(" | ".join(unique), quote=True)
    return f' data-tag-info="{escaped}" class="has-tag-info"'

  def _render_primitive(self, elem, accumulated_tags: list) -> str:
    tag = elem.tag
    tf = self._get_transform(elem)
    elem_tags = list(accumulated_tags)
    for lt in self._extract_local_tags(elem):
      if lt not in elem_tags:
        elem_tags.append(lt)

    tag_attr = self._build_tag_attr(elem_tags)

    if tag in ("multistateIndicator", "pilotedListIndicator"):
      x = round(float(elem.attrib.get("left", 0)), 1)
      y = round(float(elem.attrib.get("top", 0)), 1)
      w = round(float(elem.attrib.get("width", 0)), 1)
      h = round(float(elem.attrib.get("height", 0)), 1)

      conn = elem.find(".//connection")
      tag_expr = conn.attrib.get("expression") if conn is not None else None
      active_id = str(
          self.tag_overrides.get(
              tag_expr, elem.attrib.get("currentStateId", "0")
          )
      )

      matched_state = None
      for s in elem.findall(".//state"):
        if (
            s.attrib.get("stateId") == active_id
            or s.attrib.get("value") == active_id
        ):
          matched_state = s
          break
      if matched_state is None:
        matched_state = elem.find(".//state")

      bg = (
          matched_state.attrib.get("backColor", "navy")
          if matched_state is not None
          else "navy"
      )
      cap_node = (
          matched_state.find(".//caption") if matched_state is not None else None
      )
      raw_text = (
          cap_node.attrib.get("caption", "") if cap_node is not None else ""
      )
      txt_color = (
          cap_node.attrib.get("color", "white")
          if cap_node is not None
          else "white"
      )
      size = (
          int(cap_node.attrib.get("fontSize", 10))
          if cap_node is not None
          else 10
      )
      bold = (
          "bold"
          if cap_node is not None and cap_node.attrib.get("bold") == "true"
          else "normal"
      )

      clean_text = raw_text.replace("&#xA;", "\n").replace("\r\n", "\n")
      lines = clean_text.split("\n")
      out = [
          f"<g {tf} {tag_attr}>",
          (
              f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{bg}"'
              ' stroke="#000000" stroke-width="1"/>'
          ),
          (
              f'<polyline points="{x},{y+h} {x},{y} {x+w},{y}"'
              ' stroke="rgba(255,255,255,0.6)" stroke-width="1.5" fill="none"/>'
          ),
          (
              f'<polyline points="{x},{y+h} {x+w},{y+h} {x+w},{y}"'
              ' stroke="rgba(0,0,0,0.6)" stroke-width="1.5" fill="none"/>'
          ),
      ]
      total_h = len(lines) * (size + 4)
      start_y = y + (h / 2) - (total_h / 2) + size
      for i, line in enumerate(lines):
        line_y = round(start_y + i * (size + 4), 1)
        out.append(
            f'<text x="{round(x + w/2, 1)}" y="{line_y}" font-family="Segoe UI,'
            f' Arial, sans-serif" font-size="{size}px" font-weight="{bold}"'
            f' fill="{txt_color}" text-anchor="middle"'
            f' text-rendering="geometricPrecision">{html.escape(line)}</text>'
        )
      out.append("</g>")
      return "".join(out)

    elif tag in ("rectangle", "roundedRectangle", "panel"):
      x = round(float(elem.attrib.get("left", 0)), 1)
      y = round(float(elem.attrib.get("top", 0)), 1)
      w = round(float(elem.attrib.get("width", 0)), 1)
      h = round(float(elem.attrib.get("height", 0)), 1)
      is_trans = elem.attrib.get("backStyle") == "transparent"
      fill = "none" if is_trans else elem.attrib.get("backColor", "#FFFFFF")
      stroke = elem.attrib.get("foreColor", "none") if not is_trans else "none"
      lw = elem.attrib.get("lineWidth", "1")
      rx = round(float(elem.attrib.get("cornerRadius", 0)), 1)
      rx_attr = f'rx="{rx}" ry="{rx}"' if rx > 0 else ""
      return (
          f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"'
          f' stroke="{stroke}" stroke-width="{lw}" {rx_attr} {tf}'
          f" {tag_attr}/>"
      )

    elif tag == "line":
      pts = elem.attrib.get("line", "").strip().split()
      if len(pts) >= 4:
        stroke = (
            elem.attrib.get("backColor")
            or elem.attrib.get("foreColor")
            or "#000000"
        )
        lw = elem.attrib.get("lineWidth", "1")
        return (
            f'<line x1="{pts[0]}" y1="{pts[1]}" x2="{pts[2]}" y2="{pts[3]}"'
            f' stroke="{stroke}" stroke-width="{lw}" stroke-linecap="square"'
            f" {tf} {tag_attr}/>"
        )

    elif tag in ("polygon", "polyline"):
      raw = elem.attrib.get("path", "").strip().split()
      if len(raw) >= 4:
        coords = " ".join(
            [f"{raw[i]},{raw[i+1]}" for i in range(0, len(raw) - 1, 2)]
        )
        fill = (
            elem.attrib.get("backColor", "#999999")
            if tag == "polygon"
            else "none"
        )
        stroke = elem.attrib.get("foreColor", "#000000")
        lw = elem.attrib.get("lineWidth", "1")
        tag_name = "polygon" if tag == "polygon" else "polyline"
        return (
            f'<{tag_name} points="{coords}" fill="{fill}" stroke="{stroke}"'
            f' stroke-width="{lw}" {tf} {tag_attr}/>'
        )

    elif tag in ("ellipse", "circle"):
      l = round(float(elem.attrib.get("left", 0)), 1)
      t_pos = round(float(elem.attrib.get("top", 0)), 1)
      w = round(float(elem.attrib.get("width", 0)), 1)
      h = round(float(elem.attrib.get("height", 0)), 1)
      rx, ry = round(w / 2, 1), round(h / 2, 1)
      cx, cy = round(l + rx, 1), round(t_pos + ry, 1)
      fill = (
          elem.attrib.get("backColor", "#777777")
          if elem.attrib.get("backStyle") != "transparent"
          else "none"
      )
      stroke = elem.attrib.get("foreColor", "#000000")
      lw = elem.attrib.get("lineWidth", "1")
      return (
          f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{fill}"'
          f' stroke="{stroke}" stroke-width="{lw}" {tf} {tag_attr}/>'
      )

    elif tag == "arc":
      l = round(float(elem.attrib.get("left", 0)), 1)
      t_pos = round(float(elem.attrib.get("top", 0)), 1)
      w = round(float(elem.attrib.get("width", 0)), 1)
      h = round(float(elem.attrib.get("height", 0)), 1)
      start = float(elem.attrib.get("startAngle", 0))
      end = float(elem.attrib.get("endAngle", 0))
      rx, ry = w / 2, h / 2
      cx, cy = l + rx, t_pos + ry
      stroke = elem.attrib.get("foreColor", "#000000")
      lw = elem.attrib.get("lineWidth", "1")

      if abs(start - end) < 0.001 or abs(abs(end - start) - 2 * math.pi) < 0.01:
        fill = (
            elem.attrib.get("backColor", "#777777")
            if elem.attrib.get("backStyle") != "transparent"
            else "none"
        )
        return (
            f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{fill}"'
            f' stroke="{stroke}" stroke-width="{lw}" {tf} {tag_attr}/>'
        )
      else:
        x1 = round(cx + rx * math.cos(start), 1)
        y1 = round(cy - ry * math.sin(start), 1)
        x2 = round(cx + rx * math.cos(end), 1)
        y2 = round(cy - ry * math.sin(end), 1)
        large_arc = 1 if abs(end - start) > math.pi else 0
        sweep = 0 if end > start else 1
        return (
            f'<path d="M {x1} {y1} A {rx} {ry} 0 {large_arc} {sweep} {x2} {y2}"'
            f' fill="none" stroke="{stroke}" stroke-width="{lw}" {tf}'
            f" {tag_attr}/>"
        )

    elif tag == "text":
      x = round(float(elem.attrib.get("left", 0)), 1)
      y = round(float(elem.attrib.get("top", 0)), 1)
      w = round(float(elem.attrib.get("width", 0)), 1)
      h = round(float(elem.attrib.get("height", 0)), 1)
      size = int(
          elem.attrib.get("fontSize") or elem.attrib.get("charHeight") or 11
      )
      raw_text = elem.attrib.get("caption", "")
      clean_text = raw_text.replace("&#xA;", "\n").replace("\r\n", "\n")
      lines = clean_text.split("\n")
      color = elem.attrib.get("foreColor", "#000000")
      bold = "bold" if elem.attrib.get("bold") == "true" else "normal"
      anchor = "middle" if w > 0 else "start"
      anchor_x = round(x + (w / 2 if w > 0 else 0), 1)

      tspans = []
      total_h = len(lines) * (size + 3)
      start_y = (
          (y + h / 2 - total_h / 2 + size) if h > 0 else (y + size)
      )
      for i, line in enumerate(lines):
        line_y = round(start_y + i * (size + 3), 1)
        tspans.append(
            f'<text x="{anchor_x}" y="{line_y}" font-family="Segoe UI, Arial,'
            f' sans-serif" font-size="{size}px" font-weight="{bold}"'
            f' fill="{color}" text-anchor="{anchor}"'
            f' text-rendering="geometricPrecision">{html.escape(line)}</text>'
        )
      return f"<g {tf} {tag_attr}>" + "".join(tspans) + "</g>"

    elif tag in (
        "button",
        "momentaryButton",
        "maintainedButton",
        "latchedButton",
        "interlockingButton",
        "rampButton",
        "numericInputCursorButton",
    ):
      x = round(float(elem.attrib.get("left", 0)), 1)
      y = round(float(elem.attrib.get("top", 0)), 1)
      w = round(float(elem.attrib.get("width", 0)), 1)
      h = round(float(elem.attrib.get("height", 0)), 1)
      up = elem.find(".//up")
      bg = up.attrib.get("backColor", "#D4D0C8") if up is not None else "#D4D0C8"
      fg = up.attrib.get("foreColor", "#000000") if up is not None else "#000000"
      cap_elem = elem.find(".//caption")
      raw_cap = cap_elem.attrib.get("caption", "") if cap_elem is not None else ""
      clean_cap = raw_cap.replace("&#xA;", "\n").replace("\r\n", "\n")
      size = (
          int(cap_elem.attrib.get("fontSize", 10))
          if cap_elem is not None
          else 10
      )
      lines = clean_cap.split("\n")
      out = [
          f'<g class="hmi-button" {tf} {tag_attr}>',
          f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{bg}"/>',
          (
              f'<polyline points="{x},{y+h} {x},{y} {x+w},{y}" stroke="#FFFFFF"'
              ' stroke-width="2" fill="none"/>'
          ),
          (
              f'<polyline points="{x},{y+h} {x+w},{y+h} {x+w},{y}"'
              ' stroke="#404040" stroke-width="2" fill="none"/>'
          ),
      ]
      start_y = y + h / 2 - (len(lines) * (size + 2)) / 2 + size
      for i, line in enumerate(lines):
        out.append(
            f'<text x="{round(x + w/2, 1)}" y="{round(start_y + i*(size+2), 1)}"'
            ' font-family="Segoe UI, Arial, sans-serif"'
            f' font-size="{size}px" font-weight="bold" fill="{fg}"'
            f' text-anchor="middle"'
            f' text-rendering="geometricPrecision">{html.escape(line)}</text>'
        )
      out.append("</g>")
      return "".join(out)

    elif tag in (
        "numericDisplay",
        "stringDisplay",
        "numericInput",
        "stringInput",
    ):
      x = round(float(elem.attrib.get("left", 0)), 1)
      y = round(float(elem.attrib.get("top", 0)), 1)
      w = round(float(elem.attrib.get("width", 0)), 1)
      h = round(float(elem.attrib.get("height", 0)), 1)
      size = int(elem.attrib.get("charHeight", 12))
      fg = elem.attrib.get("foreColor", "#000000")
      bg = elem.attrib.get("backColor", "#FFFFFF")
      conn = elem.find(".//connection")
      expr = conn.attrib.get("expression", "") if conn is not None else ""
      val = str(self.tag_overrides.get(expr, "0.0"))
      is_input = "Input" in tag
      border_stroke = "#000000" if is_input else "none"
      return (
          f"<g {tf} {tag_attr}>"
          f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{bg}"'
          f' stroke="{border_stroke}" stroke-width="1"/>'
          f'<text x="{round(x + w/2, 1)}" y="{round(y + h/2 + size/3, 1)}"'
          ' font-family="Consolas, monospace" font-size="{size}px"'
          f' font-weight="bold" fill="{fg}" text-anchor="middle"'
          f' text-rendering="geometricPrecision">{val}</text>'
          "</g>"
      )

    elif tag in ("barGraph", "gauge", "trend"):
      x = round(float(elem.attrib.get("left", 0)), 1)
      y = round(float(elem.attrib.get("top", 0)), 1)
      w = round(float(elem.attrib.get("width", 0)), 1)
      h = round(float(elem.attrib.get("height", 0)), 1)
      bg = elem.attrib.get("backColor", "#1a1a1a")
      label = tag.upper()
      return (
          f"<g {tf} {tag_attr}>"
          f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{bg}"'
          ' stroke="#FFFFFF" stroke-width="1"/>'
          f'<text x="{round(x + w/2, 1)}" y="{round(y + h/2, 1)}"'
          ' font-family="Consolas, monospace" font-size="10px" fill="#888888"'
          f' text-anchor="middle">[{label}]</text>'
          "</g>"
      )

    elif tag in ("image", "symbol"):
      x = round(float(elem.attrib.get("left", 0)), 1)
      y = round(float(elem.attrib.get("top", 0)), 1)
      w = round(float(elem.attrib.get("width", 0)), 1)
      h = round(float(elem.attrib.get("height", 0)), 1)
      name = elem.attrib.get("imageName") or elem.attrib.get("name") or "SYMBOL"
      return (
          f"<g {tf} {tag_attr}>"
          f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#111111"'
          ' stroke="#555555" stroke-width="1" stroke-dasharray="2,2"/>'
          f'<text x="{round(x + w/2, 1)}" y="{round(y + h/2, 1)}"'
          ' font-family="Consolas, monospace" font-size="9px" fill="#AAAAAA"'
          f' text-anchor="middle">{html.escape(name)}</text>'
          "</g>"
      )

    elif "left" in elem.attrib and "top" in elem.attrib:
      x = round(float(elem.attrib.get("left", 0)), 1)
      y = round(float(elem.attrib.get("top", 0)), 1)
      w = round(float(elem.attrib.get("width", 10)), 1)
      h = round(float(elem.attrib.get("height", 10)), 1)
      return (
          f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none"'
          f' stroke="none" {tf} {tag_attr}/>'
      )

    return ""

  def _render_node(self, node, accumulated_tags: list) -> list:
    if node.tag in (
        "displaySettings",
        "vbaProject",
        "parameters",
        "securitySettings",
        "connections",
        "animations",
        "transform",
    ):
      return []

    current_tags = list(accumulated_tags)
    for lt in self._extract_local_tags(node):
      if lt not in current_tags:
        current_tags.append(lt)

    if node.tag == "group":
      tf = self._get_transform(node)
      tag_attr = self._build_tag_attr(current_tags)
      children_markup = []
      for child in node:
        children_markup.extend(self._render_node(child, current_tags))

      if children_markup:
        return [
            f"<g {tf} {tag_attr}>\n"
            + "\n  ".join(children_markup)
            + "\n</g>"
        ]
      return []
    else:
      rendered = self._render_primitive(node, current_tags)
      return [rendered] if rendered else []

  def compile_svg_bundle(self) -> dict:
    all_primitives = []
    for child in self.root:
      all_primitives.extend(self._render_node(child, []))
    return {
        "svg": "\n  ".join(all_primitives),
        "width": self.width,
        "height": self.height,
        "bg_color": self.bg_color,
        "file_name": self.file_name,
    }


class FTViewDatabaseHub:

  def __init__(self):
    self.lock = threading.RLock()
    app_dir = get_app_data_path()
    self.db_path = os.path.join(app_dir, "hmitagfinder.db")
    self._init_db()

  def _connect(self):
    conn = sqlite3.connect(self.db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn

  def _init_db(self):
    with self.lock:
      conn = self._connect()
      try:
        cur = conn.cursor()
        cur.execute("""
                    CREATE TABLE IF NOT EXISTS display_files (
                        display_name TEXT PRIMARY KEY,
                        display_normalized TEXT,
                        xml_bytes BLOB
                    )
                """)
        cur.execute("""
                    CREATE TABLE IF NOT EXISTS hmi_elements (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        display_name TEXT,
                        display_normalized TEXT,
                        label_text TEXT,
                        tags TEXT
                    )
                """)

        cur.execute("PRAGMA table_info(display_files);")
        df_cols = [row[1] for row in cur.fetchall()]
        if "display_normalized" not in df_cols:
          cur.execute(
              "ALTER TABLE display_files ADD COLUMN display_normalized TEXT;"
          )

        cur.execute("PRAGMA table_info(hmi_elements);")
        he_cols = [row[1] for row in cur.fetchall()]
        if "display_normalized" not in he_cols:
          cur.execute(
              "ALTER TABLE hmi_elements ADD COLUMN display_normalized TEXT;"
          )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_disp_files ON"
            " display_files(display_normalized)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_norm ON"
            " hmi_elements(display_normalized)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_disp ON hmi_elements(display_name)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_lbl ON hmi_elements(label_text)"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tags ON hmi_elements(tags)")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
      finally:
        conn.close()

  def normalize_display_name(self, name: str) -> str:
    base = os.path.splitext(name)[0]
    return re.sub(r"[^a-zA-Z0-9]", "", base).lower()

  def extract_ft_tags_from_text(self, text_val: str) -> list:
    if not text_val:
      return []
    tag_pattern = r"\{([A-Za-z0-9_#/@\.\:\[\]\-\s\$\%]+)\}"
    bracketed = re.findall(tag_pattern, text_val)
    results = []
    for b in bracketed:
      clean_b = b.strip()
      if clean_b and not clean_b.isdigit() and clean_b not in results:
        results.append(clean_b)
    if not results and text_val.startswith("/") and "::" in text_val:
      results.append(text_val.strip("{}"))
    return results

  def parse_and_index_xml(self, file_path: str):
    display_name = os.path.basename(file_path)
    with open(file_path, "rb") as f:
      xml_bytes = f.read()

    norm_name = self.normalize_display_name(display_name)
    tree = ET.parse(io.BytesIO(xml_bytes))
    root = tree.getroot()

    rows_to_insert = []
    for elem in root.iter():
      texts = []
      cap = elem.attrib.get("caption")
      if cap:
        clean = (
            cap.replace("&#xA;", "\n")
            .replace("\r\n", "\n")
            .strip()
        )
        if clean:
          texts.append(clean)

      for sub_cap in elem.findall(".//caption"):
        sc = sub_cap.attrib.get("caption", "").strip()
        if sc and sc not in texts:
          texts.append(sc)

      tags = []
      for attr_name, attr_val in elem.attrib.items():
        if isinstance(attr_val, str):
          for t in self.extract_ft_tags_from_text(attr_val):
            if t not in tags:
              tags.append(t)

      for conn in elem.findall("./connections/connection"):
        expr = conn.attrib.get("expression") or conn.attrib.get("tag")
        if expr:
          extracted = self.extract_ft_tags_from_text(expr)
          if extracted:
            tags.extend([x for x in extracted if x not in tags])
          elif expr not in tags:
            tags.append(expr)

      for anim in elem.findall("./animations/*"):
        expr = anim.attrib.get("expression") or anim.attrib.get("tag")
        if expr:
          extracted = self.extract_ft_tags_from_text(expr)
          if extracted:
            tags.extend([x for x in extracted if x not in tags])
          elif expr not in tags:
            tags.append(expr)

      for act in elem.findall("./action"):
        t = act.attrib.get("tag")
        if t:
          extracted = self.extract_ft_tags_from_text(t)
          if extracted:
            tags.extend([x for x in extracted if x not in tags])
          elif t not in tags:
            tags.append(t)

      for cmd in elem.findall("./command"):
        for attr in ("pressAction", "releaseAction"):
          c = cmd.attrib.get(attr)
          if c:
            extracted = self.extract_ft_tags_from_text(c)
            if extracted:
              tags.extend([x for x in extracted if x not in tags])
            elif c not in tags:
              tags.append(c)

      if texts or tags:
        label_text_col = "\n".join(texts)
        tags_col = " | ".join(tags)
        rows_to_insert.append(
            (display_name, norm_name, label_text_col, tags_col)
        )

    with self.lock:
      conn = self._connect()
      try:
        cur = conn.cursor()
        cur.execute(
            """
                    INSERT OR REPLACE INTO display_files (display_name, display_normalized, xml_bytes)
                    VALUES (?, ?, ?)
                """,
            (display_name, norm_name, xml_bytes),
        )
        cur.execute(
            "DELETE FROM hmi_elements WHERE display_name = ?", (display_name,)
        )
        if rows_to_insert:
          cur.executemany(
              """
                        INSERT INTO hmi_elements (display_name, display_normalized, label_text, tags)
                        VALUES (?, ?, ?, ?)
                        """,
              rows_to_insert,
          )
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
      finally:
        conn.close()

  def get_xml_bytes(self, display_name: str) -> bytes:
    with self.lock:
      conn = self._connect()
      try:
        cur = conn.cursor()
        cur.execute(
            "SELECT xml_bytes FROM display_files WHERE display_name = ?",
            (display_name,),
        )
        row = cur.fetchone()
        return row[0] if row else None
      finally:
        conn.close()

  def get_summary(self):
    with self.lock:
      conn = self._connect()
      try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM display_files")
        displays_count = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM hmi_elements")
        elements_count = cur.fetchone()[0] or 0
        return {"displays": displays_count, "elements": elements_count}
      finally:
        conn.close()

  def clear_database(self):
    with self.lock:
      conn = self._connect()
      try:
        cur = conn.cursor()
        cur.execute("DELETE FROM hmi_elements;")
        cur.execute("DELETE FROM display_files;")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        return {"displays": 0, "elements": 0}
      finally:
        conn.close()

  def get_all_displays(self):
    with self.lock:
      conn = self._connect()
      try:
        cur = conn.cursor()
        cur.execute(
            "SELECT display_name, display_normalized FROM display_files ORDER"
            " BY display_name"
        )
        rows = cur.fetchall()
        return [
            {"display_name": r[0], "display_normalized": r[1]} for r in rows
        ]
      finally:
        conn.close()

  def search_by_display(self, query: str = ""):
    query_str = (query or "").strip()
    if not query_str:
      return self.get_all_displays()

    norm_q = self.normalize_display_name(query_str)
    with self.lock:
      conn = self._connect()
      try:
        cur = conn.cursor()
        cur.execute(
            """
                    SELECT display_name, display_normalized FROM display_files 
                    WHERE display_normalized LIKE ? OR display_name LIKE ?
                    ORDER BY display_name LIMIT 100
                    """,
            (f"%{norm_q}%", f"%{query_str}%"),
        )
        rows = cur.fetchall()
        return [
            {"display_name": r[0], "display_normalized": r[1]} for r in rows
        ]
      finally:
        conn.close()

  def search_by_label(self, query: str = ""):
    query_str = (query or "").strip()
    if not query_str:
      return []
    with self.lock:
      conn = self._connect()
      try:
        cur = conn.cursor()
        cur.execute(
            """
                    SELECT display_name, label_text, tags 
                    FROM hmi_elements 
                    WHERE label_text LIKE ? 
                    ORDER BY display_name LIMIT 100
                    """,
            (f"%{query_str}%",),
        )
        rows = cur.fetchall()
        return [
            {"display_name": r[0], "label_text": r[1], "tags": r[2]}
            for r in rows
        ]
      finally:
        conn.close()

  def search_by_tag(self, query: str = ""):
    query_str = (query or "").strip()
    if not query_str:
      return []
    with self.lock:
      conn = self._connect()
      try:
        cur = conn.cursor()
        cur.execute(
            """
                    SELECT display_name, label_text, tags 
                    FROM hmi_elements 
                    WHERE tags LIKE ? 
                    ORDER BY display_name LIMIT 100
                    """,
            (f"%{query_str}%",),
        )
        rows = cur.fetchall()
        return [
            {"display_name": r[0], "label_text": r[1], "tags": r[2]}
            for r in rows
        ]
      finally:
        conn.close()


class DesktopAppBridge:

  def __init__(self, db: FTViewDatabaseHub):
    self.db = db
    self.window = None
    self.import_state = {
        "active": False,
        "current_file": "",
        "current_index": 0,
        "total_files": 0,
        "percent": 0,
        "done": False,
        "displays": 0,
        "elements": 0,
    }

  def get_initial_data(self):
    summary = self.db.get_summary()
    displays = self.db.get_all_displays()
    return {
        "displays_count": summary["displays"],
        "elements_count": summary["elements"],
        "displays": displays,
    }

  def open_import_dialog(self):
    if not self.window:
      return {"started": False}

    file_types = ("FactoryTalk XML Files (*.xml)", "All files (*.*)")
    try:
      result = self.window.create_file_dialog(
          webview.OPEN_DIALOG, allow_multiple=True, file_types=file_types
      )
    except Exception as e:
      print(f"Dialog error: {e}")
      return {"started": False, "canceled": True}

    if not result:
      return {"started": False, "canceled": True}

    file_paths = list(result)
    total = len(file_paths)
    self.import_state = {
        "active": True,
        "current_file": "Initializing...",
        "current_index": 0,
        "total_files": total,
        "percent": 0,
        "done": False,
        "displays": 0,
        "elements": 0,
    }

    def worker():
      try:
        for idx, fp in enumerate(file_paths):
          fname = os.path.basename(fp)
          self.import_state["current_file"] = fname
          self.import_state["current_index"] = idx + 1
          self.import_state["percent"] = int(((idx + 1) / total) * 100)
          try:
            self.db.parse_and_index_xml(fp)
          except Exception as parse_err:
            print(f"Error parsing {fname}: {parse_err}")

        summary = self.db.get_summary()
        self.import_state["displays"] = summary["displays"]
        self.import_state["elements"] = summary["elements"]
      except Exception as worker_err:
        print(f"Worker execution error: {worker_err}")
      finally:
        self.import_state["done"] = True
        self.import_state["active"] = False

    threading.Thread(target=worker, daemon=True).start()
    return {"started": True, "total": total}

  def get_import_status(self):
    return self.import_state

  def clear_database(self):
    return self.db.clear_database()

  def search_displays(self, query=""):
    return self.db.search_by_display(query)

  def search_labels(self, query=""):
    return self.db.search_by_label(query)

  def search_tags(self, query=""):
    return self.db.search_by_tag(query)

  def get_screen_render_data(self, display_name):
    xml_bytes = self.db.get_xml_bytes(display_name)
    if not xml_bytes:
      return None
    compiler = FlattenedFTViewCompiler(xml_bytes, display_name)
    return compiler.compile_svg_bundle()


MAIN_PORTAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>HMITagFinder</title>
    <style>
        * { 
            box-sizing: border-box; 
            margin: 0; 
            padding: 0; 
            border-radius: 0px !important; 
            -webkit-font-smoothing: antialiased;
            text-rendering: geometricPrecision;
        }
        body {
            background-color: #000000;
            color: #FFFFFF;
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Arial, sans-serif;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
            user-select: text;
        }
        header {
            background-color: #000000;
            border-bottom: 2px solid #FFFFFF;
            padding: 10px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            z-index: 10;
        }
        .header-title { display: flex; flex-direction: column; }
        .header-title h1 { font-size: 17px; font-weight: 700; color: #FFFFFF; letter-spacing: 0.5px; }
        .header-title .author-badge { font-size: 12px; color: #AAAAAA; margin-top: 2px; }
        .header-title .author-badge b { color: #FFFFFF; }
        .header-actions { display: flex; gap: 8px; align-items: center; }
        .btn {
            background-color: #FFFFFF;
            color: #000000;
            border: 2px solid #FFFFFF;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 700;
            font-family: 'Segoe UI', Arial, sans-serif;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .btn:hover { background-color: #000000; color: #FFFFFF; }
        .btn-nav { background: #000000; color: #FFFFFF; border: 1px solid #FFFFFF; }
        .btn-nav:hover { background: #FFFFFF; color: #000000; }
        .btn-danger { background: #000000; color: #FF4444; border: 1px solid #FF4444; font-size: 11px; padding: 6px 10px; }
        .btn-danger:hover { background: #FF4444; color: #000000; }

        .container { display: flex; flex: 1; overflow: hidden; position: relative; }
        
        .sidebar {
            width: 220px;
            background: #000000;
            border-right: 2px solid #FFFFFF;
            display: flex;
            flex-direction: column;
            padding: 12px 8px;
            gap: 6px;
        }
        .nav-item {
            display: flex;
            align-items: center;
            padding: 8px 12px;
            color: #FFFFFF;
            font-size: 13px;
            font-weight: 600;
            border: 1px solid transparent;
            cursor: pointer;
        }
        .nav-item:hover { border: 1px solid #FFFFFF; }
        .nav-item.active { background-color: #FFFFFF; color: #000000; border: 1px solid #FFFFFF; font-weight: 700; }

        .main-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            padding: 16px;
            overflow-y: auto;
            background: #000000;
        }
        .stats-bar { display: flex; gap: 12px; margin-bottom: 14px; }
        .stat-card {
            background: #000000;
            border: 1px solid #FFFFFF;
            padding: 8px 14px;
            display: flex;
            flex-direction: column;
            gap: 2px;
            min-width: 160px;
        }
        .stat-label { font-size: 11px; text-transform: uppercase; color: #AAAAAA; font-weight: 700; }
        .stat-value { font-size: 18px; font-weight: 700; color: #FFFFFF; font-family: 'Consolas', monospace; }

        .search-box-wrapper { margin-bottom: 12px; }
        .search-input {
            width: 100%;
            padding: 10px 12px;
            background: #000000;
            border: 2px solid #FFFFFF;
            color: #FFFFFF;
            font-size: 14px;
            font-family: 'Segoe UI', Arial, sans-serif;
            outline: none;
        }
        .search-input:focus { background: #111111; }

        .results-container {
            flex: 1;
            background: #000000;
            border: 2px solid #FFFFFF;
            overflow: auto;
        }
        table { width: 100%; border-collapse: collapse; font-size: 12px; text-align: left; }
        th {
            background-color: #FFFFFF;
            color: #000000;
            padding: 8px 12px;
            font-weight: 700;
            border-bottom: 2px solid #FFFFFF;
            position: sticky;
            top: 0;
            z-index: 2;
            text-transform: uppercase;
        }
        td { padding: 8px 12px; border-bottom: 1px solid #333333; color: #FFFFFF; vertical-align: top; }
        
        tbody tr:nth-child(even) { background-color: #141414; }
        tbody tr:nth-child(odd) { background-color: #000000; }
        tbody tr:hover td { background-color: #262626; }

        .screen-link { color: #FFFFFF; font-weight: 700; cursor: pointer; text-decoration: underline; }
        .screen-link:hover { background-color: #FFFFFF; color: #000000; }
        .tag-pill {
            display: inline-block;
            background: #000000;
            color: #FFFFFF;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            padding: 2px 6px;
            border: 1px solid #777777;
            margin: 2px 0;
            word-break: break-all;
        }
        .text-preview { white-space: pre-line; color: #DDDDDD; font-size: 12px; }
        .empty-state { padding: 30px; text-align: center; color: #888888; font-size: 13px; }

        /* Progress Modal */
        #progress-modal {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0,0,0,0.85);
            z-index: 500;
            justify-content: center;
            align-items: center;
        }
        .progress-box {
            background: #000000;
            border: 2px solid #FFFFFF;
            padding: 20px;
            width: 440px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .progress-track {
            width: 100%;
            height: 14px;
            background: #000000;
            overflow: hidden;
            border: 1px solid #FFFFFF;
        }
        .progress-fill {
            height: 100%;
            width: 0%;
            background: #FFFFFF;
            transition: width 0.05s ease;
        }

        /* Screen Viewer Fullscreen Stage Overlay */
        #screen-viewer-view {
            display: none;
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            background: #000000;
            z-index: 100;
            flex-direction: column;
        }
        .viewer-top-bar {
            height: 40px;
            background: #000000;
            border-bottom: 2px solid #FFFFFF;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 14px;
            color: #FFFFFF;
            font-size: 13px;
        }
        .viewer-stage {
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 10px;
            overflow: hidden;
            background: #111111;
            position: relative;
        }
        #screen-svg-canvas {
            width: 100%;
            height: 100%;
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            border: 1px solid #FFFFFF;
        }
        .has-tag-info { cursor: pointer; }
        .show-tags .has-tag-info { outline: 2px dashed #FFFFFF !important; }
        .has-tag-info:hover { outline: 2px solid #FFFFFF !important; }
        #viewer-tag-tooltip {
            position: fixed;
            bottom: 12px;
            left: 50%;
            transform: translateX(-50%);
            background: #000000;
            color: #FFFFFF;
            border: 1px solid #FFFFFF;
            padding: 6px 12px;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            display: none;
            z-index: 150;
            pointer-events: none;
        }

        /* Scanner Display Loader */
        #screen-loader {
            display: none;
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.88);
            z-index: 200;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            gap: 16px;
        }
        .scanner-box {
            width: 220px;
            height: 28px;
            border: 2px solid #FFFFFF;
            position: relative;
            background: #000000;
            overflow: hidden;
        }
        .scanner-bar {
            width: 60px;
            height: 100%;
            background: #FFFFFF;
            position: absolute;
            animation: scanAnimation 1.2s infinite ease-in-out alternate;
        }
        @keyframes scanAnimation {
            0% { left: 0px; }
            100% { left: 160px; }
        }
        .scanner-text {
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: #FFFFFF;
        }

        /* Rustic Overlay Windows */
        #screen-fallback, #clear-db-modal {
            display: none;
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.9);
            z-index: 250;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            padding: 24px;
            text-align: center;
        }
        #clear-db-modal {
            position: fixed;
            z-index: 600;
        }
        .fallback-box {
            border: 3px solid #FFFFFF;
            padding: 32px 48px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 16px;
            background: #000000;
            max-width: 580px;
        }
        .sad-face-ascii {
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 48px;
            font-weight: 900;
            letter-spacing: -2px;
            color: #FFFFFF;
            line-height: 1;
        }
        .skull-ascii {
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 32px;
            font-weight: 900;
            color: #FFFFFF;
            line-height: 1.1;
            white-space: pre;
        }
        .fallback-msg {
            font-family: 'Consolas', monospace;
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: #FFFFFF;
        }
        .fallback-sub {
            font-size: 12px;
            color: #888888;
            font-family: 'Consolas', monospace;
        }

        /* Inspector Modal */
        #inspector-modal {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0, 0, 0, 0.85);
            z-index: 300;
            justify-content: center;
            align-items: center;
        }
        .modal-box {
            background: #000000;
            border: 2px solid #FFFFFF;
            width: 90%;
            max-width: 620px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .modal-header {
            background: #FFFFFF;
            color: #000000;
            padding: 8px 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            font-weight: 700;
        }
        .modal-body { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
        .modal-body textarea {
            width: 100%;
            height: 140px;
            background: #000000;
            color: #FFFFFF;
            border: 1px solid #FFFFFF;
            padding: 8px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            line-height: 1.4;
            resize: vertical;
            outline: none;
        }
        .modal-footer { display: flex; justify-content: space-between; align-items: center; }

        /* Custom Context Menu */
        #custom-context-menu {
            display: none;
            position: fixed;
            background: #000000;
            border: 2px solid #FFFFFF;
            padding: 2px 0;
            z-index: 1000;
            min-width: 150px;
        }
        .context-menu-item {
            padding: 6px 12px;
            font-size: 12px;
            color: #FFFFFF;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .context-menu-item:hover { background-color: #FFFFFF; color: #000000; }
        .context-menu-divider { height: 1px; background: #555555; margin: 2px 0; }
    </style>
</head>
<body>

    <header>
        <div class="header-title">
            <h1>HMITagFinder</h1>
            <div class="author-badge">Created by <b>Luis Castillo</b></div>
        </div>
        <div class="header-actions">
            <button class="btn btn-danger" onclick="openClearDatabaseModal()">Clear Database</button>
            <button class="btn" onclick="startLoadingBatch()">Load & Parse XML Files</button>
        </div>
    </header>

    <div class="container">
        <div class="sidebar">
            <div class="nav-item active" id="tab-displays" onclick="switchTab('displays')">Display Names</div>
            <div class="nav-item" id="tab-labels" onclick="switchTab('labels')">Label & Text Search</div>
            <div class="nav-item" id="tab-tags" onclick="switchTab('tags')">PLC Tag Cross-Ref</div>
        </div>

        <div class="main-content">
            <div class="stats-bar">
                <div class="stat-card">
                    <span class="stat-label">Loaded Displays</span>
                    <span class="stat-value" id="stat-displays">0</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Indexed Elements</span>
                    <span class="stat-value" id="stat-elements">0</span>
                </div>
            </div>

            <div class="search-box-wrapper">
                <input type="text" id="main-search-input" class="search-input" 
                       placeholder="Search displays (ignores dashes, underscores, and spaces)..." 
                       oninput="onSearchInputDebounced(this.value)">
            </div>

            <div class="results-container">
                <table id="results-table">
                    <thead id="table-head">
                        <tr><th>Display Name</th><th>Normalized Identifier</th><th>Action</th></tr>
                    </thead>
                    <tbody id="table-body">
                        <tr><td colspan="3" class="empty-state">No displays indexed. Click "Load & Parse XML Files" to begin.</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- SVG Viewer Overlay Stage -->
        <div id="screen-viewer-view">
            <div class="viewer-top-bar">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <button class="btn btn-nav" onclick="closeScreenViewer()">BACK TO SEARCH</button>
                    <span id="viewer-screen-title"><b>Screen:</b></span>
                </div>
                <div>
                    <button id="toggle-tag-btn" class="btn btn-nav" onclick="toggleTagOverlay()">Toggle Tag Highlight Box</button>
                </div>
            </div>
            <div class="viewer-stage">
                <div id="screen-loader">
                    <div class="scanner-box">
                        <div class="scanner-bar"></div>
                    </div>
                    <div class="scanner-text" id="loader-title">Rendering Display...</div>
                </div>

                <div id="screen-fallback">
                    <div class="fallback-box">
                        <div class="sad-face-ascii">:(</div>
                        <div class="fallback-msg">looks like you are screwed</div>
                        <div class="fallback-sub">Display rendering took too long or encountered invalid XML structure.</div>
                        <div style="display: flex; gap: 10px; margin-top: 8px;">
                            <button class="btn" onclick="retryCurrentScreen()">Retry Load</button>
                            <button class="btn btn-nav" onclick="closeScreenViewer()">Back to Search</button>
                        </div>
                    </div>
                </div>

                <svg id="screen-svg-canvas" preserveAspectRatio="xMidYMid meet"></svg>
            </div>
        </div>
    </div>

    <!-- Rustic Warning Modal for Database Clearing -->
    <div id="clear-db-modal">
        <div class="fallback-box">
            <div class="skull-ascii">[ ! ]
 /_\\ </div>
            <div class="fallback-msg">warning: purge database</div>
            <div class="fallback-sub">Are you out of your mind? There ain't no way back from this.</div>
            <div style="display: flex; gap: 10px; margin-top: 8px;">
                <button class="btn btn-danger" onclick="executeClearDatabase()">Confirm Clear</button>
                <button class="btn btn-nav" onclick="closeClearDatabaseModal()">Cancel</button>
            </div>
        </div>
    </div>

    <!-- Progress Modal -->
    <div id="progress-modal">
        <div class="progress-box">
            <h3 style="font-size: 13px; color: #FFFFFF; text-transform: uppercase;">Parsing & Indexing XML Files...</h3>
            <div class="progress-track">
                <div class="progress-fill" id="progress-fill"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 11px; color: #AAAAAA; font-family: 'Consolas', monospace;">
                <span id="progress-status-file">Processing...</span>
                <span id="progress-status-count">0 / 0</span>
            </div>
        </div>
    </div>

    <!-- Inspector Modal -->
    <div id="viewer-tag-tooltip"></div>
    <div id="inspector-modal" onclick="closeInspectorModal()">
        <div class="modal-box" onclick="event.stopPropagation()">
            <div class="modal-header">
                <span>Element Tag & Expression Inspector</span>
                <button class="btn" onclick="closeInspectorModal()" style="padding: 1px 6px; font-size: 10px;">✕</button>
            </div>
            <div class="modal-body">
                <textarea id="modal-tag-textarea" spellcheck="false"></textarea>
                <div class="modal-footer">
                    <span id="copy-status" style="color: #FFFFFF; font-size: 11px; display: none;">[ Copied to clipboard ]</span>
                    <div style="margin-left: auto; display: flex; gap: 6px;">
                        <button class="btn" onclick="copyAllText()">Copy All</button>
                        <button class="btn btn-nav" onclick="closeInspectorModal()">Close</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Custom Context Menu -->
    <div id="custom-context-menu">
        <div class="context-menu-item" onclick="contextCopySelection()">Copy Selection <span>Ctrl+C</span></div>
        <div class="context-menu-item" onclick="contextCopyAll()">Copy All <span>Ctrl+A, C</span></div>
        <div class="context-menu-divider"></div>
        <div class="context-menu-item" onclick="contextSelectAll()">Select All</div>
    </div>

    <script>
        let currentTab = 'displays';
        let overlayActive = false;
        let isInspectorOpen = false;
        let searchDebounceTimer = null;
        let currentDisplayLoading = null;
        let renderTimeoutTimer = null;
        let isInitialLoaded = false;
        let isInitialLoading = false;
        let isImporting = false;

        function escapeJsString(str) {
            return (str || '').replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'");
        }

        async function requestInitialLoad() {
            if (isInitialLoaded || isInitialLoading) return;
            if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_initial_data) {
                setTimeout(requestInitialLoad, 150);
                return;
            }

            isInitialLoading = true;
            try {
                const data = await window.pywebview.api.get_initial_data();
                if (data) {
                    isInitialLoaded = true;
                    document.getElementById('stat-displays').textContent = data.displays_count || 0;
                    document.getElementById('stat-elements').textContent = data.elements_count || 0;
                    renderDisplaysTable(data.displays || []);
                }
            } catch (e) {
                console.error("Initial load error:", e);
            } finally {
                isInitialLoading = false;
            }
        }

        window.addEventListener('pywebviewready', requestInitialLoad);
        document.addEventListener('DOMContentLoaded', requestInitialLoad);

        function renderDisplaysTable(results) {
            const tbody = document.getElementById('table-body');
            const thead = document.getElementById('table-head');
            thead.innerHTML = `<tr><th>Display Name</th><th>Normalized Identifier</th><th>Action</th></tr>`;
            
            if (!results || results.length === 0) {
                tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No displays indexed. Click "Load & Parse XML Files" to begin.</td></tr>`;
                return;
            }
            tbody.innerHTML = results.map(r => `
                <tr>
                    <td><b>${r.display_name}</b></td>
                    <td style="font-family: 'Consolas', monospace; color: #AAAAAA;">${r.display_normalized}</td>
                    <td><span class="screen-link" onclick="openScreen('${escapeJsString(r.display_name)}')">[ Launch Screen ]</span></td>
                </tr>
            `).join('');
        }

        async function switchTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            const activeNav = document.getElementById('tab-' + tab);
            if (activeNav) activeNav.classList.add('active');

            const searchInput = document.getElementById('main-search-input');
            const thead = document.getElementById('table-head');
            
            if (tab === 'displays') {
                searchInput.placeholder = "Search displays (ignores dashes, underscores, and spaces)...";
                thead.innerHTML = `<tr><th>Display Name</th><th>Normalized Identifier</th><th>Action</th></tr>`;
            } else if (tab === 'labels') {
                searchInput.placeholder = "Type text to find all screens where this caption appears...";
                thead.innerHTML = `<tr><th>Display</th><th>Label / Caption Found</th><th>Associated Tag(s)</th></tr>`;
            } else if (tab === 'tags') {
                searchInput.placeholder = "Search by PLC tag e.g. /CH01/Data_1::[CH01_042] or Status...";
                thead.innerHTML = `<tr><th>Display</th><th>PLC Tag / Expression</th><th>Associated Text</th></tr>`;
            }
            await performSearch(searchInput.value || '');
        }

        function onSearchInputDebounced(val) {
            clearTimeout(searchDebounceTimer);
            searchDebounceTimer = setTimeout(() => {
                performSearch(val);
            }, 250);
        }

        async function startLoadingBatch() {
            if (isImporting) return;
            let resp;
            try {
                resp = await window.pywebview.api.open_import_dialog();
            } catch (e) {
                console.error("Dialog error:", e);
                document.getElementById('progress-modal').style.display = 'none';
                return;
            }

            if (!resp || !resp.started) {
                document.getElementById('progress-modal').style.display = 'none';
                return;
            }

            isImporting = true;
            document.getElementById('progress-modal').style.display = 'flex';
            document.getElementById('progress-fill').style.width = '0%';
            document.getElementById('progress-status-file').textContent = 'Starting parsing...';
            document.getElementById('progress-status-count').textContent = '0 / ' + resp.total;

            pollImportStatus();
        }

        async function pollImportStatus() {
            if (!isImporting) return;
            try {
                const st = await window.pywebview.api.get_import_status();
                if (st) {
                    document.getElementById('progress-status-file').textContent = st.current_file || 'Processing...';
                    document.getElementById('progress-status-count').textContent = (st.current_index || 0) + ' / ' + (st.total_files || 0);
                    document.getElementById('progress-fill').style.width = (st.percent || 0) + '%';

                    if (st.done) {
                        isImporting = false;
                        document.getElementById('progress-modal').style.display = 'none';
                        document.getElementById('stat-displays').textContent = st.displays;
                        document.getElementById('stat-elements').textContent = st.elements;
                        await performSearch(document.getElementById('main-search-input').value || '');
                        return;
                    }
                }
            } catch (err) {
                console.error("Poll error:", err);
            }

            if (isImporting) {
                setTimeout(pollImportStatus, 200);
            }
        }

        function openClearDatabaseModal() {
            document.getElementById('clear-db-modal').style.display = 'flex';
        }

        function closeClearDatabaseModal() {
            document.getElementById('clear-db-modal').style.display = 'none';
        }

        async function executeClearDatabase() {
            closeClearDatabaseModal();
            try {
                const stats = await window.pywebview.api.clear_database();
                document.getElementById('stat-displays').textContent = stats.displays || 0;
                document.getElementById('stat-elements').textContent = stats.elements || 0;
                await performSearch('');
            } catch (e) {
                console.error("Clear DB error:", e);
            }
        }

        async function performSearch(query) {
            if (!window.pywebview || !window.pywebview.api) return;
            const tbody = document.getElementById('table-body');
            const thead = document.getElementById('table-head');
            const cleanQuery = (query || "").trim();

            try {
                if (currentTab === 'displays') {
                    const results = await window.pywebview.api.search_displays(cleanQuery);
                    renderDisplaysTable(results);

                } else if (currentTab === 'labels') {
                    thead.innerHTML = `<tr><th>Display</th><th>Label / Caption Found</th><th>Associated Tag(s)</th></tr>`;
                    if (!cleanQuery) {
                        tbody.innerHTML = `<tr><td colspan="3" class="empty-state">Type text above to search screen labels.</td></tr>`;
                        return;
                    }
                    const results = await window.pywebview.api.search_labels(cleanQuery);
                    if (!results || results.length === 0) {
                        tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No screens found containing "${cleanQuery}".</td></tr>`;
                        return;
                    }
                    tbody.innerHTML = results.map(r => `
                        <tr>
                            <td><span class="screen-link" onclick="openScreen('${escapeJsString(r.display_name)}')">${r.display_name}</span></td>
                            <td class="text-preview">${escapeHtml(r.label_text)}</td>
                            <td>${formatTags(r.tags)}</td>
                        </tr>
                    `).join('');

                } else if (currentTab === 'tags') {
                    thead.innerHTML = `<tr><th>Display</th><th>PLC Tag / Expression</th><th>Associated Text</th></tr>`;
                    if (!cleanQuery) {
                        tbody.innerHTML = `<tr><td colspan="3" class="empty-state">Type a tag pattern above to cross-reference displays.</td></tr>`;
                        return;
                    }
                    const results = await window.pywebview.api.search_tags(cleanQuery);
                    if (!results || results.length === 0) {
                        tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No screens found referencing "${cleanQuery}".</td></tr>`;
                        return;
                    }
                    tbody.innerHTML = results.map(r => `
                        <tr>
                            <td><span class="screen-link" onclick="openScreen('${escapeJsString(r.display_name)}')">${r.display_name}</span></td>
                            <td>${formatTags(r.tags)}</td>
                            <td class="text-preview">${escapeHtml(r.label_text || '-')}</td>
                        </tr>
                    `).join('');
                }
            } catch (err) {
                console.error("Search error:", err);
            }
        }

        async function openScreen(displayName) {
            currentDisplayLoading = displayName;
            clearTimeout(renderTimeoutTimer);

            const screenView = document.getElementById('screen-viewer-view');
            const loader = document.getElementById('screen-loader');
            const fallback = document.getElementById('screen-fallback');
            const loaderTitle = document.getElementById('loader-title');
            const svg = document.getElementById('screen-svg-canvas');

            loaderTitle.textContent = `Loading ${displayName}...`;
            svg.innerHTML = '';
            fallback.style.display = 'none';
            loader.style.display = 'flex';
            screenView.style.display = 'flex';

            renderTimeoutTimer = setTimeout(() => {
                loader.style.display = 'none';
                fallback.style.display = 'flex';
            }, 6000);

            setTimeout(async () => {
                try {
                    const data = await window.pywebview.api.get_screen_render_data(displayName);
                    clearTimeout(renderTimeoutTimer);

                    if (data) {
                        svg.setAttribute('viewBox', `0 0 ${data.width} ${data.height}`);
                        svg.style.backgroundColor = data.bg_color;
                        svg.innerHTML = data.svg;
                        document.getElementById('viewer-screen-title').innerHTML = `<b>Screen:</b> ${data.file_name} (${data.width}×${data.height})`;
                        loader.style.display = 'none';
                        fallback.style.display = 'none';
                    } else {
                        loader.style.display = 'none';
                        fallback.style.display = 'flex';
                    }
                } catch (e) {
                    clearTimeout(renderTimeoutTimer);
                    loader.style.display = 'none';
                    fallback.style.display = 'flex';
                }
            }, 50);
        }

        function retryCurrentScreen() {
            if (currentDisplayLoading) {
                openScreen(currentDisplayLoading);
            }
        }

        function closeScreenViewer() {
            clearTimeout(renderTimeoutTimer);
            document.getElementById('screen-viewer-view').style.display = 'none';
            document.getElementById('screen-fallback').style.display = 'none';
            document.getElementById('screen-loader').style.display = 'none';
        }

        function toggleTagOverlay() {
            overlayActive = !overlayActive;
            document.getElementById('screen-viewer-view').classList.toggle('show-tags', overlayActive);
            document.getElementById('toggle-tag-btn').textContent = overlayActive ? 'Hide Tag Outlines' : 'Toggle Tag Highlight Box';
        }

        const tooltip = document.getElementById('viewer-tag-tooltip');
        const inspectorModal = document.getElementById('inspector-modal');
        const modalTextarea = document.getElementById('modal-tag-textarea');
        const copyStatus = document.getElementById('copy-status');
        const contextMenu = document.getElementById('custom-context-menu');

        document.addEventListener('mouseover', (e) => {
            if (isInspectorOpen) return;
            const target = e.target.closest('[data-tag-info]');
            if (target && document.getElementById('screen-viewer-view').style.display === 'flex') {
                tooltip.style.display = 'block';
                tooltip.textContent = target.getAttribute('data-tag-info');
            }
        });

        document.addEventListener('mouseout', (e) => {
            if (isInspectorOpen) return;
            const target = e.target.closest('[data-tag-info]');
            if (target) tooltip.style.display = 'none';
        });

        document.addEventListener('click', (e) => {
            hideContextMenu();
            const target = e.target.closest('[data-tag-info]');
            if (target && document.getElementById('screen-viewer-view').style.display === 'flex') {
                e.stopPropagation();
                const rawInfo = target.getAttribute('data-tag-info');
                if (rawInfo) {
                    modalTextarea.value = rawInfo.split(' | ').join('\\n');
                    inspectorModal.style.display = 'flex';
                    isInspectorOpen = true;
                    tooltip.style.display = 'none';
                    copyStatus.style.display = 'none';
                    setTimeout(() => {
                        modalTextarea.focus();
                        modalTextarea.select();
                    }, 50);
                }
            }
        });

        modalTextarea.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            contextMenu.style.top = e.clientY + 'px';
            contextMenu.style.left = e.clientX + 'px';
            contextMenu.style.display = 'block';
        });

        function hideContextMenu() {
            contextMenu.style.display = 'none';
        }

        function executeCopy(textToCopy) {
            if (!textToCopy) return;
            const temp = document.createElement("textarea");
            temp.value = textToCopy;
            document.body.appendChild(temp);
            temp.select();
            try {
                document.execCommand("copy");
                showCopiedFeedback();
            } catch (err) {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(textToCopy).then(showCopiedFeedback);
                }
            }
            document.body.removeChild(temp);
            hideContextMenu();
        }

        function showCopiedFeedback() {
            copyStatus.style.display = 'inline';
            setTimeout(() => { copyStatus.style.display = 'none'; }, 2000);
        }

        function contextCopySelection() {
            const start = modalTextarea.selectionStart;
            const end = modalTextarea.selectionEnd;
            const selectedText = modalTextarea.value.substring(start, end) || modalTextarea.value;
            executeCopy(selectedText);
        }

        function contextCopyAll() {
            executeCopy(modalTextarea.value);
        }

        function copyAllText() {
            executeCopy(modalTextarea.value);
        }

        function contextSelectAll() {
            modalTextarea.select();
            hideContextMenu();
        }

        function closeInspectorModal() {
            inspectorModal.style.display = 'none';
            isInspectorOpen = false;
            hideContextMenu();
        }

        function formatTags(tagString) {
            if (!tagString) return '<span style="color:#666666;">None</span>';
            return tagString.split(' | ').map(t => `<div class="tag-pill">${escapeHtml(t)}</div>`).join('');
        }

        function escapeHtml(text) {
            return (text || '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                hideContextMenu();
                closeClearDatabaseModal();
                if (isInspectorOpen) closeInspectorModal();
                else if (document.getElementById('screen-viewer-view').style.display === 'flex') closeScreenViewer();
            }
        });
    </script>
</body>
</html>"""


def main():
  db = FTViewDatabaseHub()
  bridge = DesktopAppBridge(db)

  window = webview.create_window(
      title="HMITagFinder - Created by Luis Castillo",
      html=MAIN_PORTAL_HTML,
      js_api=bridge,
      width=1360,
      height=860,
      resizable=True,
      text_select=True,
  )
  bridge.window = window

  webview.start()


if __name__ == "__main__":
  main()
