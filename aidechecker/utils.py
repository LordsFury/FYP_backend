from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from datetime import datetime
import re
import pytz

local_timezone = pytz.timezone("Asia/Karachi")

def convert_aide_timestamps(line):
    match = re.search(r'(Start|End)\s+timestamp:\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
    if match:
        label = match.group(1)
        utc_str = match.group(2)
        try:
            utc_dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
            utc_dt = pytz.utc.localize(utc_dt)
            local_dt = utc_dt.astimezone(local_timezone)
            return f"{label} timestamp: {local_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception:
            return line
    return line


def _make_on_page(generated_on_text):
    def _on_page(c, doc):
        c.saveState()
        width, height = letter
        outer_margin = 20   
        inner_margin_gap = 6

        c.setStrokeColor(colors.black)

        c.setLineWidth(2)
        c.rect(
            outer_margin,
            outer_margin,
            width - 2 * outer_margin,
            height - 2 * outer_margin
        )

        c.setLineWidth(1.2)
        inner_margin = outer_margin + inner_margin_gap
        c.rect(
            inner_margin,
            inner_margin,
            width - 2 * inner_margin,
            height - 2 * inner_margin
        )

        footer_y = outer_margin - 12

        c.setFont("Helvetica-Bold", 9)
        c.drawString(outer_margin, footer_y, "AIDE Report")

        c.setFont("Helvetica-Oblique", 9)
        c.drawCentredString(width / 2.0, footer_y, generated_on_text)

        page_num = c.getPageNumber()
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(width - outer_margin, footer_y, f"Page {page_num}")

        c.restoreState()
    return _on_page



def format_ts_in_string(val: str) -> str:
    try:
        dt = datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S %z")

        local_dt = dt.astimezone(local_timezone)

        return local_dt.strftime("%d-%m-%Y %H:%M:%S")
    except Exception:
        return val

def _parse_aide_output(lines):
    summary = {
        "Files Added": 0,
        "Files Removed": 0,
        "Files Changed": 0,
        "Total Files Scanned": 0,
        "Start Timestamp": None,
        "End Timestamp": None,
    }

    details = {
        "Added Files": [],
        "Removed Files": [],
        "Changed Files": [],
        "Detailed Info": [],
        "DB Attributes": [],
    }

    db_info = []
    current_section = None

    re_total = re.compile(r"Total number of entries:\s*(\d+)", re.I)
    re_changed_heading = re.compile(r"^Changed entries\s*:\s*(\d+)", re.I)
    re_added_heading   = re.compile(r"^Added entries\s*:\s*(\d+)", re.I)
    re_removed_heading = re.compile(r"^Removed entries\s*:\s*(\d+)", re.I)
    re_section = re.compile(
        r"^(Added entries|Removed entries|Changed entries|Detailed information about changes|The attributes of the.*)",
        re.I,
    )
    re_start = re.compile(r"^Start timestamp:\s*(.*)", re.I)
    re_end = re.compile(r"^End timestamp:\s*(.*)", re.I)

    for raw in lines:
        line = raw.strip()

        if re_start.match(line):
            raw_ts = re_start.match(line).group(1).strip()
            try:
                summary["Start Timestamp"] = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S").strftime("%d-%m-%Y %H:%M:%S")
            except ValueError:
                summary["Start Timestamp"] = raw_ts
            continue
        if re_end.match(line):
            raw_ts = re_end.match(line).group(1).strip()
            try:
                summary["End Timestamp"] = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S").strftime("%d-%m-%Y %H:%M:%S")
            except ValueError:
                summary["End Timestamp"] = raw_ts
            continue
        if re_total.match(line):
            summary["Total Files Scanned"] = int(re_total.match(line).group(1))
            continue
        if re_changed_heading.match(line):
            summary["Files Changed"] = int(re_changed_heading.match(line).group(1))
            continue
        if re_added_heading.match(line):
            summary["Files Added"] = int(re_added_heading.match(line).group(1))
            continue
        if re_removed_heading.match(line):
            summary["Files Removed"] = int(re_removed_heading.match(line).group(1))
            continue

        if "database and filesystem" in line.lower():
            db_info.append(line)
            continue

        m = re_section.match(line)
        if m:
            header = m.group(1).lower()
            if header.startswith("added"):
                current_section = "Added Files"
            elif header.startswith("removed"):
                current_section = "Removed Files"
            elif header.startswith("changed"):
                current_section = "Changed Files"
            elif header.startswith("detailed information"):
                current_section = "Detailed Info"
            elif header.startswith("the attributes"):
                current_section = "DB Attributes"
            continue

        if current_section:
            details[current_section].append(line)

    return summary, details, db_info


def _normalize_detailed_info(details):
    structured = []
    current_file = None
    current_type = None
    changes = []

    for line in details["Detailed Info"]:
        if line.startswith(("Directory:", "File:", "Link:")):
            if current_file is not None:
                structured.append({
                    "type": current_type,
                    "path": current_file,
                    "changes": changes
                })

            prefix, value = line.split(":", 1)
            current_type = prefix.strip()
            current_file = value.strip()
            changes = []
            continue
        if ":" in line and "|" in line:
            key, values = line.split(":", 1)
            try:
                old_val, new_val = values.split("|", 1)
            except ValueError:
                old_val, new_val = values, ""
            changes.append({
                "attribute": key.strip(),
                "old": format_ts_in_string(old_val.strip()),
                "new": format_ts_in_string(new_val.strip())
            })

    if current_file is not None:
        structured.append({
            "type": current_type,
            "path": current_file,
            "changes": changes
        })

    return structured


def format_aide_data(lines):
    summary, details, db_info = _parse_aide_output(lines)
    normalized_details = _normalize_detailed_info(details)

    db_attrs = {}
    current_key = None
    for line in details["DB Attributes"]:
        if ":" in line:
            key, value = line.split(":", 1)
            db_attrs[key.strip()] = value.strip()
            current_key = key.strip()
        elif current_key:
            db_attrs[current_key] += line.strip()

    return {
        "summary": summary,
        "details": {
            "Added Files": details["Added Files"],
            "Removed Files": details["Removed Files"],
            "Changed Files": details["Changed Files"],
            "Detailed Info": normalized_details
        },
        "db_info": db_info,
        "db_attributes": db_attrs
    }


def _make_file_list_table(title, file_list, styles):
    if not file_list:
        return None
        
    story = []
    
    data = [[title]]
    for file_path in file_list:
        cleaned_path = re.sub(r'^[-•\s]+', '', file_path).strip()
        data.append([cleaned_path])
    
    table = Table(data, colWidths=[480])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#283593")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 12),
        ("ALIGN", (0,0), (-1,-1), "LEFT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("BACKGROUND", (0,1), (-1,-1), colors.HexColor("#e8eaf6")),
        ("FONTSIZE", (0,1), (-1,-1), 10),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 12))
    return story


def _make_detailed_info_tables(details, styles):
    tables = []
    
    for item in details["Detailed Info"]:
        file_type = item["type"]
        file_path = item["path"]
        changes = item["changes"]
        
        if not changes:
            continue
            
        tables.append(Paragraph(f"<b>{file_type}: {file_path}</b>", styles["RptSmallHeading"]))
        
        data = [["Attribute", "Old Value", "New Value"]]
        for change in changes:
            data.append([change["attribute"], change["old"], change["new"]])
        
        table = Table(data, colWidths=[100, 180, 180])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#283593")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,0), 12),
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ("BACKGROUND", (0,1), (-1,-1), colors.HexColor("#e8eaf6")),
            ("FONTSIZE", (0,1), (-1,-1), 10),
        ]))
        tables.append(table)
        tables.append(Spacer(1, 12))

    return tables


def _make_attr_reference():
    rows = [
        ["Attribute", "Meaning"],
        ["mtime", "Last modification time of the file"],
        ["ctime", "Last inode change time"],
        ["atime", "Last access time"],
        ["perms", "File permissions"],
        ["uid/gid", "User ID / Group ID owner"],
        ["sha256", "SHA-256 checksum of file contents"],
        ["size", "File size in bytes"],
        ["inode", "Filesystem inode number"],
    ]

    tbl = Table(rows, colWidths=[120, 360])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#4527a0")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 12),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("BACKGROUND", (0,1), (-1,-1), colors.HexColor("#ede7f6")),
        ("FONTSIZE", (0,1), (-1,-1), 10),
    ]))
    return tbl


def save_report_as_pdf(filepath, lines):
    formatted_data = format_aide_data(lines)
    
    generated_on = datetime.now(local_timezone).strftime("%d-%m-%Y %H:%M:%S")
    summary = formatted_data["summary"]
    details = formatted_data["details"]
    db_info = formatted_data["db_info"]
    db_attrs = formatted_data["db_attributes"]

    doc = SimpleDocTemplate(
        filepath,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="RptTitle",
        fontSize=24,
        alignment=1,
        textColor=colors.HexColor("#1a237e"),
        fontName="Helvetica-Bold",
        spaceAfter=20,
    ))
    styles.add(ParagraphStyle(
        name="RptSubtitle",
        fontSize=12,
        alignment=1,
        textColor=colors.grey,
        spaceAfter=20,
    ))
    styles.add(ParagraphStyle(
        name="RptHeading",
        fontSize=14,
        textColor=colors.HexColor("#1a237e"),
        fontName="Helvetica-Bold",
        spaceBefore=4,
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(name="RptBody", fontSize=11, leading=15))
    styles.add(ParagraphStyle(
        name="RptSubSection",
        fontSize=12,
        leftIndent=20,
        textColor=colors.HexColor("#b71c1c"),
        fontName="Helvetica-Bold",
        spaceBefore=8,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(name="RptMono", fontSize=10, leftIndent=40, fontName="Courier"))
    styles.add(ParagraphStyle(
        name="RptDBInfo",
        fontSize=12,
        fontName="Helvetica",
        leftIndent=20,
        textColor=colors.black,
        spaceBefore=10,
    ))
    styles.add(ParagraphStyle(
        name="RptSmallHeading",
        fontSize=12,
        fontName="Helvetica-Bold",
        leftIndent=20,
        textColor=colors.black,
        spaceBefore=10,
        spaceAfter=10,
    ))

    story = []
    story.append(Paragraph("AIDE Scan Report", styles["RptTitle"]))
    story.append(Paragraph(f"Generated on {generated_on}", styles["RptSubtitle"]))

    # Summary table
    story.append(Paragraph("Summary", styles["RptHeading"]))
    data = [
        ["Metric", "Value"],
        ["Total Files Scanned", str(summary.get("Total Files Scanned", 0))],
        ["Files Added", str(summary.get("Files Added", 0))],
        ["Files Removed", str(summary.get("Files Removed", 0))],
        ["Files Changed", str(summary.get("Files Changed", 0))],
    ]
    if summary.get("Start Timestamp"):
        data.append(["Start Timestamp", summary["Start Timestamp"]])
    if summary.get("End Timestamp"):
        data.append(["End Timestamp", summary["End Timestamp"]])

    summary_table = Table(data, colWidths=[200, 280])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#283593")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 12),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BACKGROUND", (0,1), (-1,-1), colors.HexColor("#e8eaf6")),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("FONTSIZE", (0,1), (-1,-1), 11),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 18))

    if db_info:
        story.append(Paragraph("Database Information:", styles["RptHeading"]))
        for info_line in db_info:
            story.append(Paragraph(info_line, styles["RptDBInfo"]))
        story.append(Spacer(1, 12))
    
    has_file_changes = any([
        details["Added Files"],
        details["Removed Files"],
        details["Changed Files"],
        details["Detailed Info"]
    ])
    
    if has_file_changes:
        story.append(Paragraph("File Changes", styles["RptHeading"]))
        
        if details["Added Files"]:
            added_table = _make_file_list_table("Added Files", details["Added Files"], styles)
            if added_table:
                story.extend(added_table)
        
        if details["Removed Files"]:
            removed_table = _make_file_list_table("Removed Files", details["Removed Files"], styles)
            if removed_table:
                story.extend(removed_table)
        
        if details["Changed Files"]:
            changed_table = _make_file_list_table("Changed Files", details["Changed Files"], styles)
            if changed_table:
                story.extend(changed_table)

    if details["Detailed Info"]:
        if has_file_changes:
            story.append(PageBreak())
        story.append(Paragraph("Detailed Differences about Changes", styles["RptHeading"]))
        story.extend(_make_detailed_info_tables(details, styles))
        story.append(Spacer(1, 18))

    if db_attrs:
        story.append(PageBreak())
        story.append(Paragraph("Database Attributes", styles["RptHeading"]))

        data = [["Attribute", "Value"]]
        for key, value in db_attrs.items():
            para_value = Paragraph(value, ParagraphStyle(
                name="DBHash",
                fontName="Helvetica",
                fontSize=9,
                textColor=colors.black,
                leading=11,
            ))
            data.append([key, para_value])

        db_table = Table(data, colWidths=[120, 360])
        db_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#283593")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("ALIGN", (0,0), (-1,0), "CENTER"),
            ("FONTSIZE", (0,0), (-1,0), 12),
            ("TEXTCOLOR", (0,1), (-1,-1), colors.black),
            ("ALIGN", (0,1), (-1,-1), "CENTER"),
            ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
            ("FONTSIZE", (0,1), (-1,-1), 11),
            ("BACKGROUND", (0,1), (-1,-1), colors.HexColor("#e8eaf6")),
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        story.append(db_table)
        story.append(Spacer(1, 80))

    story.append(Paragraph("Attributes Reference", styles["RptHeading"]))
    story.append(_make_attr_reference())

    on_page = _make_on_page(f"Generated on {generated_on}")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)

    return filepath



def extract_rules(config_path):
    rules = []
    # valid rule tokens: letters/numbers, usually short like p,i,n,sha256,sha512
    rule_pattern = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*([A-Za-z0-9\+]+)$")

    with open(config_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            match = rule_pattern.match(line)
            if match:
                rhs = match.group(2)
                if "+" in rhs:
                    rules.append(match.group(1))

    return sorted(set(rules))
