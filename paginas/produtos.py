"""Página: Produtos (cadastrar, editar e excluir)."""
import streamlit as st

from nucleo import servicos
from nucleo.modelos import ItemTI

from . import ui


def mostrar(ctx):
    if not ctx.pode_editar:
        st.error("Seu perfil não tem permissão para gerir produtos.")
        return
    produtos = ctx.produtos
    col_add, col_edit = st.columns(2, gap="large")
    categorias_op = ui.opcoes_categoria(produtos)

    # ---------------------------------------------------------- cadastro
    with col_add:
        st.subheader("➕ Cadastrar novo produto")
        with st.form("form_cadastro", clear_on_submit=True):
            novo_nome = st.text_input("Nome do equipamento:", placeholder="Ex: MOUSE USB")
            cat_escolhida = st.selectbox("Categoria:", categorias_op)
            nova_cat = st.text_input("Ou crie uma nova categoria (opcional):")
            f1, f2 = st.columns(2)
            estoque_inicial = f1.number_input("Estoque inicial:", min_value=0, value=0, step=1)
            estoque_min = f2.number_input("Alerta a partir de:", min_value=0, value=2, step=1)
            controla = st.checkbox("Controlar por número de série / patrimônio (ex.: notebook, desktop)")
            series_ini = st.text_area("Números de série iniciais (um por linha — só se controlar por série):")
            enviar = st.form_submit_button("➕ Adicionar produto")

        if enviar:
            nome = novo_nome.upper().strip()
            categoria = nova_cat.strip() or cat_escolhida
            if not nome:
                st.error("Informe o nome do equipamento.")
            elif nome in produtos:
                st.error(f"'{nome}' já está cadastrado.")
            else:
                inicial = 0 if controla else int(estoque_inicial)
                produtos[nome] = ItemTI(nome, categoria, inicial, estoque_min, controla)
                servicos.registrar(ctx.historico, nome, "🆕 Cadastro", ctx.usuario_id, inicial, 0, inicial)
                msg = f"Produto '{nome}' cadastrado com sucesso!"
                if controla and servicos.normalizar_series(series_ini):
                    servicos.movimentar(ctx.dados, nome, "entrada", 0, ctx.usuario_id, series=series_ini)
                    msg += f" ({produtos[nome].estoque_atual} unidade(s) com número de série.)"
                ctx.salvar()
                st.session_state["mov_equip_pendente"] = nome
                ui.avisar("sucesso", msg)
                st.rerun()

    # ---------------------------------------------------------- edição / exclusão
    with col_edit:
        st.subheader("✏️ Editar / excluir produto")
        if not produtos:
            st.info("Nenhum produto para editar.")
            return
        nomes = sorted(produtos)
        ui.sincronizar_selecao("edit_equip", nomes)
        sel = st.selectbox("Produto:", nomes, key="edit_equip")
        item = produtos[sel]
        pref = f"{ctx.filial_atual}_{sel}"

        with st.form(f"form_edicao_{pref}"):
            ed_nome = st.text_input("Nome:", value=item.nome, key=f"ed_nome_{pref}")
            ed_cat = st.selectbox("Categoria:", categorias_op, index=categorias_op.index(item.categoria),
                                  key=f"ed_cat_{pref}")
            ed_nova_cat = st.text_input("Ou crie uma nova categoria (opcional):", key=f"ed_novacat_{pref}")
            ed_min = st.number_input("Alerta de reposição a partir de:", min_value=0,
                                     value=item.estoque_minimo, step=1, key=f"ed_min_{pref}")
            salvar = st.form_submit_button("💾 Salvar alterações do produto")
        if item.controla_serie:
            st.caption("🔢 Este produto é controlado por número de série (o estoque é a contagem das unidades).")

        if salvar:
            nome_novo = ed_nome.upper().strip()
            if not nome_novo:
                st.error("O nome não pode ficar vazio.")
            elif nome_novo != sel and nome_novo in produtos:
                st.error(f"Já existe um produto chamado '{nome_novo}'.")
            else:
                item.nome = nome_novo
                item.categoria = ed_nova_cat.strip() or ed_cat
                item.estoque_minimo = int(ed_min)
                reordenado = {i.nome: i for i in produtos.values()}  # a chave do dicionário é o nome
                produtos.clear()
                produtos.update(reordenado)
                detalhe = f"era: {sel}" if nome_novo != sel else ""
                servicos.registrar(ctx.historico, nome_novo, "✏️ Edição", ctx.usuario_id,
                                   anterior=item.estoque_atual, final=item.estoque_atual, detalhe=detalhe)
                ctx.salvar()
                st.session_state["edit_equip_pendente"] = nome_novo
                st.session_state["mov_equip_pendente"] = nome_novo
                ui.avisar("sucesso", f"Produto '{nome_novo}' atualizado!")
                st.rerun()

        if ctx.eh_admin:
            st.divider()
            confirmar = st.checkbox(f"Confirmo que quero excluir '{sel}'", key=f"conf_del_{pref}")
            if st.button("🗑️ Excluir produto", disabled=not confirmar, key="btn_excluir"):
                servicos.registrar(ctx.historico, sel, "🗑️ Exclusão", ctx.usuario_id, anterior=item.estoque_atual)
                del produtos[sel]
                ctx.salvar()
                ui.avisar("aviso", f"Produto '{sel}' excluído.")
                st.rerun()
