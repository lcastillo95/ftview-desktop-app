import os
import sys
import html
import math
import tkinter as tk
from tkinter import filedialog
import xml.etree.ElementTree as ET
import webview

class FlattenedFTViewCompiler:
    def __init__(self, xml_bytes: bytes, file_name: str, tag_overrides: dict = None):
        self.file_name = file_name
        self.tree = ET.parse(xml_bytes)
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

        for conn in elem.findall("./connections/connection"):
            expr = conn.attrib.get("expression")
            conn_name = conn.attrib.get("name", "Value")
            if expr:
                info.append(f"Conn ({conn_name}): {expr}")

        for anim in elem.findall("./animations/*"):
            anim_type = anim.tag.replace("animate", "")
            expr = anim.attrib.get("expression")
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

        if tag == "multistateIndicator":
            x, y = float(elem.attrib.get("left", 0)), float(elem.attrib.get("top", 0))
            w, h = float(elem.attrib.get("width", 0)), float(elem.attrib.get("height", 0))
            conn = elem.find(".//connection")
            tag_expr = conn.attrib.get("expression") if conn is not None else None
            active_id = str(self.tag_overrides.get(tag_expr, elem.attrib.get("currentStateId", "0")))

            matched_state = None
            for s in elem.findall(".//state"):
                if s.attrib.get("stateId") == active_id or s.attrib.get("value") == active_id:
                    matched_state = s
                    break
            if matched_state is None:
                matched_state = elem.find(".//state")

            bg = matched_state.attrib.get("backColor", "navy") if matched_state is not None else "navy"
            cap_node = matched_state.find(".//caption") if matched_state is not None else None
            raw_text = cap_node.attrib.get("caption", "") if cap_node is not None else ""
            txt_color = cap_node.attrib.get("color", "white") if cap_node is not None else "white"
            size = int(cap_node.attrib.get("fontSize", 10)) if cap_node is not None else 10
            bold = "bold" if cap_node is not None and cap_node.attrib.get("bold") == "true" else "normal"

            lines = raw_text.replace("
", "\n").split("\n")
            out = [
                f'',
                f'',
                f'',
                f''
            ]
            total_h = len(lines) * (size + 3)
            start_y = y + (h / 2) - (total_h / 2) + (size / 2)
            for i, line in enumerate(lines):
                line_y = start_y + i * (size + 3)
                out.append(f'{html.escape(line)}')
            out.append("")
            return "".join(out)

        elif tag == "rectangle":
            x, y = float(elem.attrib.get("left", 0)), float(elem.attrib.get("top", 0))
            w, h = float(elem.attrib.get("width", 0)), float(elem.attrib.get("height", 0))
            is_trans = elem.attrib.get("backStyle") == "transparent"
            fill = "none" if is_trans else elem.attrib.get("backColor", "#FFFFFF")
            stroke = elem.attrib.get("foreColor", "none") if not is_trans else "none"
            lw = elem.attrib.get("lineWidth", "1")
            return f''

        elif tag == "line":
            pts = elem.attrib.get("line", "").strip().split()
            if len(pts) >= 4:
                stroke = elem.attrib.get("backColor") or elem.attrib.get("foreColor") or "#000000"
                lw = elem.attrib.get("lineWidth", "1")
                return f''

        elif tag in ("polygon", "polyline"):
            raw = elem.attrib.get("path", "").strip().split()
            coords = " ".join([f"{raw[i]},{raw[i+1]}" for i in range(0, len(raw) - 1, 2)])
            fill = elem.attrib.get("backColor", "#999999") if tag == "polygon" else "none"
            stroke = elem.attrib.get("foreColor", "#000000")
            lw = elem.attrib.get("lineWidth", "1")
            tag_name = "polygon" if tag == "polygon" else "polyline"
            return f'<{tag_name} points="{coords}" fill="{fill}" stroke="{stroke}" stroke-width="{lw}" {tf} {tag_attr}/>'

        elif tag == "text":
            x, y = float(elem.attrib.get("left", 0)), float(elem.attrib.get("top", 0))
            w, h = float(elem.attrib.get("width", 0)), float(elem.attrib.get("height", 0))
            size = int(elem.attrib.get("fontSize") or elem.attrib.get("charHeight") or 11)
            lines = elem.attrib.get("caption", "").replace("
", "\n").split("\n")
            color = elem.attrib.get("foreColor", "#000000")
            bold = "bold" if elem.attrib.get("bold") == "true" else "normal"
            anchor = "middle" if w > 0 else "start"
            anchor_x = x + (w / 2 if w > 0 else 0)

            tspans = []
            total_h = len(lines) * (size + 3)
            start_y = (y + h / 2 - total_h / 2 + size / 2) if h > 0 else (y + size / 2)
            for i, line in enumerate(lines):
                line_y = start_y + i * (size + 3)
                tspans.append(f'{html.escape(line)}')
            return f'' + "".join(tspans) + ""

        elif tag == "button":
            x, y = float(elem.attrib.get("left", 0)), float(elem.attrib.get("top", 0))
            w, h = float(elem.attrib.get("width", 0)), float(elem.attrib.get("height", 0))
            up = elem.find(".//up")
            bg = up.attrib.get("backColor", "#D4D0C8") if up is not None else "#D4D0C8"
            fg = up.attrib.get("foreColor", "#000000") if up is not None else "#000000"
            cap_elem = elem.find(".//caption")
            raw_cap = cap_elem.attrib.get("caption", "").replace("
", "\n") if cap_elem is not None else ""
            size = int(cap_elem.attrib.get("fontSize", 10)) if cap_elem is not None else 10
            lines = raw_cap.split("\n")
            out = [
                f'',
                f'',
                f'',
                f''
            ]
            start_y = y + h / 2 - (len(lines) * (size + 2)) / 2 + size / 2
            for i, line in enumerate(lines):
                out.append(f'{html.escape(line)}')
            out.append("")
            return "".join(out)

        elif tag in ("numericDisplay", "stringDisplay"):
            x, y = float(elem.attrib.get("left", 0)), float(elem.attrib.get("top", 0))
            w, h = float(elem.attrib.get("width", 0)), float(elem.attrib.get("height", 0))
            size = int(elem.attrib.get("charHeight", 12))
            fg = elem.attrib.get("foreColor", "#000000")
            conn = elem.find(".//connection")
            expr = conn.attrib.get("expression", "") if conn is not None else ""
            val = str(self.tag_overrides.get(expr, "0.0"))
            return f'{val}'

        return ""

    def _flatten_and_render(self, node, accumulated_tags: list) -> list:
        rendered_elements = []
        if node.tag in ("displaySettings", "vbaProject", "animations", "connections", "transform"):
            return rendered_elements
        current_tags = list(accumulated_tags)
        for lt in self._extract_local_tags(node):
            if lt not in current_tags:
                current_tags.append(lt)

        if node.tag == "group":
            for child in node:
                rendered_elements.extend(self._flatten_and_render(child, current_tags))
        else:
            svg_markup = self._render_primitive(node, current_tags)
            if svg_markup:
                rendered_elements.append(svg_markup)
        return rendered_elements

    def compile(self) -> str:
        all_primitives = []
        for child in self.root:
            all_primitives.extend(self._flatten_and_render(child, []))
        svg_content = "\n  ".join(all_primitives)

        return f"""


    
    


    
        Screen: {self.file_name} ({self.width}×{self.height})
        Toggle Tag Highlight Box
    
    {svg_content}
    
    
        
            
                Element Tag & Expression Inspector
                ✕
            
            
                
                
                    ✓ Copied to clipboard!
                    
                        Copy All
                        Close
                    
                
            
        
    
    

"""

def select_file():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    file_path = filedialog.askopenfilename(
        title="Select FactoryTalk View XML File",
        filetypes=[("XML files", "*.xml"), ("All files", "*.*")]
    )
    root.destroy()
    return file_path

def main():
    xml_path = select_file()
    if not xml_path:
        sys.exit(0)

    file_name = os.path.basename(xml_path)
    with open(xml_path, "rb") as f:
        file_bytes = f.read()

    compiler = FlattenedFTViewCompiler(file_bytes, file_name)
    html_markup = compiler.compile()

    webview.create_window(
        title=f"FTView Screen Viewer - {file_name}",
        html=html_markup,
        width=1280,
        height=800,
        resizable=True
    )
    webview.start()

if __name__ == "__main__":
    main()
