"""Geração de PDFs (comprovante e relatório de transferências). Precisa do reportlab."""
import io
from datetime import datetime


def _txt(valor):
    """Texto seguro para a fonte padrão do PDF (mantém acentos, tira emojis e símbolos)."""
    t = str(valor).replace("—", "-").replace("–", "-").replace("→", "->")
    return "".join(c for c in t if ord(c) < 256)


def _componentes():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    return colors, A4, landscape, ParagraphStyle, getSampleStyleSheet, mm, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _tabela(dados, larguras, colors, Table, TableStyle):
    t = Table(dados, colWidths=larguras, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def pdf_comprovante(c):
    """Comprovante de uma transferência (dict devolvido por servicos.transferir_lote)."""
    colors, A4, _, ParagraphStyle, getSampleStyleSheet, mm, Paragraph, Doc, Spacer, Table, TableStyle = _componentes()
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("n", parent=estilos["Normal"], fontSize=10, leading=14)
    pequeno = ParagraphStyle("p", parent=estilos["Normal"], fontSize=8.5, leading=11)
    buf = io.BytesIO()
    doc = Doc(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
              title=f"Comprovante {c['protocolo']}")

    data, _, hora = c["data_hora"].partition(" ")
    total = sum(i["quantidade"] for i in c["itens"])
    el = [
        Paragraph("Comprovante de Transferência de Equipamentos", estilos["Title"]),
        Paragraph(f"<b>Protocolo:</b> {_txt(c['protocolo'])}", normal),
        Paragraph(f"<b>Data:</b> {data} &nbsp;&nbsp; <b>Hora:</b> {hora}", normal),
        Paragraph(f"<b>Saindo de (origem):</b> {_txt(c['origem'])}", normal),
        Paragraph(f"<b>Indo para (destino):</b> {_txt(c['destino'])}", normal),
        Paragraph(f"<b>Responsável pela transferência:</b> {_txt(c['usuario_nome'])} ({_txt(c['usuario'])})", normal),
        Paragraph(f"<b>Quem vai receber:</b> {_txt(c.get('recebedor') or '-')}", normal),
        Spacer(1, 8 * mm),
    ]
    dados = [["Produto", "Categoria", "Qtd", "Nº de série / patrimônio"]]
    for i in c["itens"]:
        dados.append([
            Paragraph(_txt(i["equipamento"]), pequeno),
            Paragraph(_txt(i["categoria"]), pequeno),
            str(i["quantidade"]),
            Paragraph(_txt(", ".join(i["series"]) or "-"), pequeno),
        ])
    el.append(_tabela(dados, [62 * mm, 38 * mm, 14 * mm, 60 * mm], colors, Table, TableStyle))
    el += [Spacer(1, 4 * mm), Paragraph(f"<b>Total:</b> {len(c['itens'])} produto(s), {total} unidade(s)", normal),
           Spacer(1, 12 * mm)]

    nome_env = f"{_txt(c['usuario_nome'])} ({_txt(c['usuario'])})"
    nome_rec = _txt(c.get("recebedor") or "")
    nome_st = ParagraphStyle("nome", parent=normal, alignment=1, fontName="Helvetica-Bold")
    peq_c = ParagraphStyle("pc", parent=pequeno, alignment=1)
    assin = Table(
        [
            ["QUEM ENVIOU", "QUEM RECEBEU"],
            ["", ""],  # espaço para assinar
            [Paragraph(nome_env, nome_st), Paragraph(nome_rec or "&nbsp;", nome_st)],
            [Paragraph("Assinatura", peq_c), Paragraph("Assinatura", peq_c)],
            [Paragraph("Data: ____/____/________", peq_c), Paragraph("Data: ____/____/________", peq_c)],
        ],
        colWidths=[85 * mm, 85 * mm],
        rowHeights=[8 * mm, 24 * mm, 9 * mm, 6 * mm, 8 * mm],
    )
    assin.setStyle(TableStyle([
        ("BOX", (0, 0), (0, -1), 0.8, colors.HexColor("#334155")),
        ("BOX", (1, 0), (1, -1), 0.8, colors.HexColor("#334155")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("LINEBELOW", (0, 1), (-1, 1), 0.6, colors.HexColor("#334155")),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
    ]))
    el += [assin, Spacer(1, 10 * mm),
           Paragraph(f"Documento gerado em {datetime.now():%d/%m/%Y %H:%M} pelo sistema TI Stock PRO.", pequeno)]
    doc.build(el)
    return buf.getvalue()


def pdf_relatorio_transferencias(df, subtitulo=""):
    """Relatório em tabela (paisagem) das transferências do DataFrame recebido."""
    colors, A4, landscape, ParagraphStyle, getSampleStyleSheet, mm, Paragraph, Doc, Spacer, Table, TableStyle = _componentes()
    estilos = getSampleStyleSheet()
    pequeno = ParagraphStyle("p", parent=estilos["Normal"], fontSize=8, leading=10)
    buf = io.BytesIO()
    doc = Doc(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm,
              bottomMargin=12 * mm, title="Relatório de transferências")
    total = int(df["Quantidade"].fillna(0).sum()) if len(df) else 0
    el = [Paragraph("Relatório de Transferências entre Filiais", estilos["Title"])]
    if subtitulo:
        el.append(Paragraph(_txt(subtitulo), pequeno))
    el += [Paragraph(f"{len(df)} registro(s) - {total} unidade(s) transferida(s)", pequeno), Spacer(1, 4 * mm)]

    colunas = ["Protocolo", "Data", "Hora", "Origem", "Destino", "Equipamento", "Quantidade", "Nº de série", "Enviado por", "Recebido por"]
    cab = ["Protocolo", "Data", "Hora", "Origem", "Destino", "Produto", "Qtd", "Nº de série", "Enviado por", "Recebido por"]
    dados = [cab]
    for _, r in df.iterrows():
        dados.append([Paragraph(_txt(r[c] if str(r[c]) != "<NA>" else ""), pequeno) for c in colunas])
    larguras = [43, 20, 17, 23, 23, 38, 9, 32, 33, 35]
    larguras = [x * mm for x in larguras]
    el.append(_tabela(dados, larguras, colors, Table, TableStyle))
    el += [Spacer(1, 6 * mm),
           Paragraph(f"Gerado em {datetime.now():%d/%m/%Y %H:%M} pelo sistema TI Stock PRO.", pequeno)]
    doc.build(el)
    return buf.getvalue()
