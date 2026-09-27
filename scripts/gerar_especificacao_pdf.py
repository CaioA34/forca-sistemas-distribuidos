"""Gera o PDF da especificação Markdown com ReportLab."""
from pathlib import Path
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted,
    KeepTogether,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs' / 'especificacao-jogo-forca.md'
OUTPUT = ROOT / 'output' / 'pdf' / 'especificacao-jogo-forca.pdf'
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

fonts = Path('C:/Windows/Fonts')
for name, filename in [('Arial', 'arial.ttf'), ('Arial-Bold', 'arialbd.ttf'),
                       ('Arial-Italic', 'ariali.ttf'), ('Arial-BoldItalic', 'arialbi.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold',
                              italic='Arial-Italic', boldItalic='Arial-BoldItalic')

styles = {
    'title': ParagraphStyle('Title', fontName='Arial-Bold', fontSize=23,
                            leading=28, textColor=colors.black, spaceAfter=12),
    'subtitle': ParagraphStyle('Subtitle', fontName='Arial', fontSize=12,
                               leading=17, spaceAfter=8),
    'meta': ParagraphStyle('Meta', fontName='Arial', fontSize=9,
                           leading=13, textColor=colors.HexColor('#555555'), spaceAfter=19),
    'h1': ParagraphStyle('H1', fontName='Arial-Bold', fontSize=15,
                         leading=19, spaceBefore=18, spaceAfter=9, keepWithNext=True),
    'h2': ParagraphStyle('H2', fontName='Arial-Bold', fontSize=11.7,
                         leading=16, spaceBefore=12, spaceAfter=7, keepWithNext=True),
    'body': ParagraphStyle('Body', fontName='Arial', fontSize=10.2,
                           leading=14.3, spaceAfter=8, allowWidows=0, allowOrphans=0),
    'list': ParagraphStyle('List', fontName='Arial', fontSize=10.2,
                           leading=14.3, spaceAfter=6, leftIndent=15, firstLineIndent=0,
                           bulletIndent=0, allowWidows=0, allowOrphans=0),
    'cell': ParagraphStyle('Cell', fontName='Arial', fontSize=9.3,
                           leading=12.4, spaceAfter=0),
    'head': ParagraphStyle('Head', fontName='Arial-Bold', fontSize=9.3,
                           leading=12.4, textColor=colors.white),
    'code': ParagraphStyle('Code', fontName='Courier', fontSize=8.8,
                           leading=12, spaceBefore=5, spaceAfter=10),
}

def markup(text):
    out = escape(text)
    out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out)
    out = re.sub(r'(https?://[^\s]+)',
                 lambda m: '<link href="' + m[1] + '" color="#244867">' + m[1] + '</link>', out)
    return out

WIDTH = A4[0] - 40*mm

def make_table(lines):
    raw = [[cell.strip() for cell in line.strip('|').split('|')] for line in lines]
    raw = [r for r in raw if not all(re.fullmatch(r'[:\- ]+', c) for c in r)]
    n = len(raw[0])
    if n == 2:
        first = max(len(row[0]) for row in raw)
        ratio = .38 if first > 25 else .30
        widths = [WIDTH*ratio, WIDTH*(1-ratio)]
    else:
        widths = [WIDTH*.10, WIDTH*.37, WIDTH*.53] if raw[0][0] == 'ID' else [WIDTH*.25, WIDTH*.29, WIDTH*.46]
    rows = [[Paragraph(markup(c), styles['head' if i == 0 else 'cell'])
             for c in row] for i, row in enumerate(raw)]
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
    commands = [('BACKGROUND', (0,0), (-1,0), colors.HexColor('#244867')),
                ('GRID', (0,0), (-1,-1), .45, colors.HexColor('#D9D9D9')),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1,-1), 8),
                ('RIGHTPADDING', (0,0), (-1,-1), 8),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6)]
    for i in range(1, len(rows)):
        commands.append(('BACKGROUND', (0,i), (-1,i),
                         colors.HexColor('#F2F5F7') if i % 2 == 0 else colors.white))
    table.setStyle(TableStyle(commands))
    return table

def page_decor(canvas, doc):
    canvas.saveState()
    canvas.setFont('Arial', 8)
    canvas.setFillColor(colors.HexColor('#555555'))
    if doc.page > 1:
        canvas.drawString(20*mm, A4[1]-13*mm, 'Jogo da forca distribuído | Especificação técnica')
    canvas.drawString(20*mm, 12*mm, 'Sistemas Distribuídos | Versão 1.0')
    canvas.drawRightString(A4[0]-20*mm, 12*mm, str(doc.page))
    canvas.restoreState()

class SpecDoc(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == 'H1':
            title = flowable.getPlainText()
            key = 'section-' + title.split(' ')[0]
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, 0, False)

lines = SOURCE.read_text(encoding='utf-8').splitlines()
story = []
i = 0
while i < len(lines):
    line = lines[i].strip()
    if not line:
        i += 1
        continue
    if line.startswith('```'):
        chunk = []
        i += 1
        while i < len(lines) and not lines[i].startswith('```'):
            chunk.append(lines[i])
            i += 1
        story.append(Preformatted('\n'.join(chunk), styles['code']))
    elif line.startswith('|'):
        block = []
        while i < len(lines) and lines[i].startswith('|'):
            block.append(lines[i])
            i += 1
        story.extend([make_table(block), Spacer(1, 9)])
        continue
    elif line.startswith('### '):
        story.append(Paragraph(markup(line[4:]), styles['h2']))
    elif line.startswith('## '):
        story.append(Paragraph(markup(line[3:]), styles['h1']))
    elif line.startswith('# '):
        story.append(Paragraph(markup(line[2:]), styles['title']))
    elif line.startswith('- '):
        story.append(Paragraph(markup(line[2:]), styles['list'], bulletText='•'))
    elif re.match(r'^\d+\. ', line):
        num, content = line.split('. ', 1)
        story.append(Paragraph(markup(content), styles['list'], bulletText=num+'.'))
    else:
        style = 'subtitle' if i == 2 else 'meta' if i == 4 else 'body'
        story.append(Paragraph(markup(line), styles[style]))
    i += 1

doc = SpecDoc(str(OUTPUT), pagesize=A4, rightMargin=20*mm,
              leftMargin=20*mm, topMargin=22*mm, bottomMargin=21*mm,
              title='Especificação do jogo da forca distribuído',
              author='Projeto de Sistemas Distribuídos',
              subject='Python, sockets, duas máquinas, VMs e Docker')
doc.build(story, onFirstPage=page_decor, onLaterPages=page_decor)
print(OUTPUT)
