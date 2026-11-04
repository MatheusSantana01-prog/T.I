"""Página: Movimentar (entrada, saída e ajuste)."""
import streamlit as st

from nucleo import config, servicos

from . import ui


def mostrar(ctx):
    if not ctx.pode_editar:
        st.error("Seu perfil não tem permissão para movimentar o estoque.")
        return
    produtos = ctx.produtos
    if not produtos:
        st.info("Nenhum produto cadastrado. Vá na página ⚙️ Produtos para cadastrar.")
        return

    col1, col2 = st.columns([1.2, 1])
    nomes = sorted(produtos)

    with col1:
        ui.sincronizar_selecao("mov_equip", nomes)
        equipamento = st.selectbox("Escolha o Equipamento:", nomes, key="mov_equip")
        item = produtos[equipamento]

        opcoes = ["📥 Entrada (Somar)", "📤 Saída (Subtrair)"]
        if not item.controla_serie:
            opcoes.append("✏️ Ajuste Direto (Definir valor exato)")
        if st.session_state.get("tipo_acao") not in opcoes:
            st.session_state.pop("tipo_acao", None)
        tipo_acao = st.radio("Modo de Edição / Operação:", opcoes, horizontal=True, key="tipo_acao")
        entrada, saida = "Entrada" in tipo_acao, "Saída" in tipo_acao
        tipo = "entrada" if entrada else "saida" if saida else "ajuste"

        # a chave muda junto com o estoque, então os campos limpam depois de salvar
        k = f"{ctx.filial_atual}_{equipamento}_{item.estoque_atual}"
        qtd, series, destino = 1, None, ""

        if item.controla_serie:
            if entrada:
                series = st.text_area("Números de série / patrimônio (um por linha):", key=f"series_ent_{k}")
            else:
                series = st.multiselect("Quais unidades estão saindo?", item.series_em_estoque(), key=f"series_sai_{k}")
        elif tipo == "ajuste":
            qtd = st.number_input("Definir Novo Estoque Total:", min_value=0, value=item.estoque_atual,
                                  step=1, key=f"qtd_ajuste_{k}")
        else:
            qtd = st.number_input("Quantidade a movimentar:", min_value=1, value=1, step=1, key=f"qtd_mov_{k}")

        if entrada:
            destino = st.text_input("Origem (fornecedor / nota fiscal) — opcional:", key=f"orig_{k}")
        elif saida:
            destino = st.text_input("Destino (setor ou pessoa que recebeu):", key=f"dest_{k}")

        if st.button("Salvar Alteração / Movimentação", key="btn_salvar_mov"):
            ok, msg = servicos.movimentar(ctx.dados, equipamento, tipo, qtd, ctx.usuario_id, destino, series)
            if ok:
                ctx.salvar()
                ui.avisar("sucesso", msg)
                st.rerun()
            else:
                st.error(msg)

    with col2:
        cor = config.COR_STATUS[item.status]
        extra = "<p><b>Controle:</b> por número de série</p>" if item.controla_serie else ""
        st.markdown(
            f"""
            <div class="card-info" style="border-left-color:{cor};">
                <h2 style='margin-top:0; color:white;'>Status atual do item</h2>
                <p><b>Nome:</b> {ui.esc(item.nome)}</p>
                <p><b>Categoria:</b> {ui.esc(item.categoria)}</p>
                <p><b>Estoque atual:</b> {item.estoque_atual} un.</p>
                <p><b>Alerta de reposição a partir de:</b> {item.estoque_minimo} un.</p>
                <p><b>Situação:</b> {item.status}</p>
                {extra}
            </div>
            """,
            unsafe_allow_html=True,
        )
        recentes = [h for h in ctx.historico if h.get("Equipamento") == equipamento][-5:]
        if recentes:
            st.caption("Últimas movimentações deste item")
            df = servicos.historico_df(recentes).iloc[::-1]
            ui.mostrar_tabela(df[["Data/Hora", "Operação", "Quantidade", "Destino/Origem", "Usuário"]])
