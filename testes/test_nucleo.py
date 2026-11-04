"""Testes da parte lógica (rodam sem Streamlit):  python -m unittest discover -s testes -t ."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from nucleo import armazenamento, config, seguranca, servicos
from nucleo.modelos import ItemTI


def filiais_exemplo():
    return {
        "Matriz": {"produtos": {"MOUSE": ItemTI("MOUSE", "Periféricos", 5),
                                "NOTEBOOK": ItemTI("NOTEBOOK", "Computadores", 0, 1, True)},
                   "historico": []},
        "Embu": {"produtos": {}, "historico": []},
    }


class TestMovimentacao(unittest.TestCase):
    def test_entrada_saida_e_ajuste(self):
        f = filiais_exemplo()["Matriz"]
        self.assertTrue(servicos.movimentar(f, "MOUSE", "entrada", 3, "ana")[0])
        self.assertEqual(f["produtos"]["MOUSE"].estoque_atual, 8)
        self.assertTrue(servicos.movimentar(f, "MOUSE", "saida", 2, "ana", destino="Financeiro")[0])
        self.assertEqual(f["produtos"]["MOUSE"].estoque_atual, 6)
        self.assertTrue(servicos.movimentar(f, "MOUSE", "ajuste", 10, "ana")[0])
        self.assertEqual(f["produtos"]["MOUSE"].estoque_atual, 10)
        self.assertEqual(len(f["historico"]), 3)
        self.assertEqual(f["historico"][1]["Destino/Origem"], "Financeiro")

    def test_saida_exige_destino_e_estoque(self):
        f = filiais_exemplo()["Matriz"]
        self.assertFalse(servicos.movimentar(f, "MOUSE", "saida", 1, "ana")[0])
        ok, msg = servicos.movimentar(f, "MOUSE", "saida", 99, "ana", destino="TI")
        self.assertFalse(ok)
        self.assertIn("insuficiente", msg)
        self.assertEqual(f["produtos"]["MOUSE"].estoque_atual, 5)
        self.assertEqual(f["historico"], [])

    def test_numero_de_serie(self):
        f = filiais_exemplo()["Matriz"]
        self.assertTrue(servicos.movimentar(f, "NOTEBOOK", "entrada", 0, "ana", series="sn1\nsn2, sn3")[0])
        nb = f["produtos"]["NOTEBOOK"]
        self.assertEqual(nb.estoque_atual, 3)
        self.assertFalse(servicos.movimentar(f, "NOTEBOOK", "entrada", 0, "ana", series="SN1")[0])
        self.assertTrue(servicos.movimentar(f, "NOTEBOOK", "saida", 0, "ana", destino="Maria", series=["SN2"])[0])
        self.assertEqual(nb.estoque_atual, 2)
        self.assertEqual(nb.unidades["SN2"]["destino"], "Maria")
        self.assertFalse(servicos.movimentar(f, "NOTEBOOK", "saida", 0, "ana", destino="X", series=["SN2"])[0])
        self.assertFalse(servicos.movimentar(f, "NOTEBOOK", "ajuste", 5, "ana")[0])
        # devolução: a mesma série pode voltar ao estoque
        self.assertTrue(servicos.movimentar(f, "NOTEBOOK", "entrada", 0, "ana", series=["SN2"])[0])
        self.assertEqual(nb.estoque_atual, 3)


class TestTransferencia(unittest.TestCase):
    def test_quantidade(self):
        f = filiais_exemplo()
        ok, _ = servicos.transferir(f, "Matriz", "Embu", "MOUSE", 2, "ana")
        self.assertTrue(ok)
        self.assertEqual(f["Matriz"]["produtos"]["MOUSE"].estoque_atual, 3)
        self.assertEqual(f["Embu"]["produtos"]["MOUSE"].estoque_atual, 2)
        self.assertEqual(f["Embu"]["produtos"]["MOUSE"].categoria, "Periféricos")
        self.assertEqual(f["Matriz"]["historico"][-1]["Operação"], "🔀 Transferência (saída)")
        self.assertEqual(f["Embu"]["historico"][-1]["Operação"], "🔀 Transferência (entrada)")

    def test_validacoes_nao_alteram_nada(self):
        f = filiais_exemplo()
        self.assertFalse(servicos.transferir(f, "Matriz", "Matriz", "MOUSE", 1, "ana")[0])
        self.assertFalse(servicos.transferir(f, "Matriz", "Embu", "MOUSE", 50, "ana")[0])
        self.assertFalse(servicos.transferir(f, "Matriz", "Embu", "INEXISTENTE", 1, "ana")[0])
        self.assertEqual(f["Embu"]["produtos"], {})
        self.assertEqual(f["Matriz"]["historico"], [])

    def test_series(self):
        f = filiais_exemplo()
        servicos.movimentar(f["Matriz"], "NOTEBOOK", "entrada", 0, "ana", series="A1,A2")
        self.assertTrue(servicos.transferir(f, "Matriz", "Embu", "NOTEBOOK", 0, "ana", series=["A1"])[0])
        self.assertEqual(f["Matriz"]["produtos"]["NOTEBOOK"].estoque_atual, 1)
        self.assertEqual(f["Embu"]["produtos"]["NOTEBOOK"].series_em_estoque(), ["A1"])
        self.assertFalse(servicos.transferir(f, "Matriz", "Embu", "NOTEBOOK", 0, "ana", series=["A1"])[0])


class TestImportacao(unittest.TestCase):
    CSV = ("Equipamento;Categoria;Estoque;Alerta\nmouse usb;Periféricos;10;3\n"
           "TECLADO;;4;\nMOUSE USB;x;1;1\n;;;\nCABO;Cabos;abc;1\n").encode("utf-8")

    def test_leitura_e_validacao(self):
        df = servicos.ler_planilha(self.CSV, "estoque.csv")
        linhas, erros = servicos.preparar_importacao(df)
        self.assertEqual([l["nome"] for l in linhas], ["MOUSE USB", "TECLADO"])
        self.assertEqual(linhas[1]["alerta"], None)
        self.assertEqual(len(erros), 2)  # repetido + estoque inválido
        self.assertTrue(any("repetido" in e for e in erros))

    def test_aplicar_modos(self):
        dados = filiais_exemplo()["Matriz"]
        linhas = [{"nome": "MOUSE", "categoria": "", "estoque": 5, "alerta": None},
                  {"nome": "TECLADO", "categoria": "", "estoque": 4, "alerta": None}]
        r = servicos.aplicar_importacao(dados, linhas, servicos.MODO_SOMAR, "ana")
        self.assertEqual((r["novos"], r["atualizados"]), (1, 1))
        self.assertEqual(dados["produtos"]["MOUSE"].estoque_atual, 10)
        self.assertEqual(dados["produtos"]["TECLADO"].categoria, "Sem categoria")
        r = servicos.aplicar_importacao(dados, linhas, servicos.MODO_SUBSTITUIR, "ana")
        self.assertEqual(dados["produtos"]["MOUSE"].estoque_atual, 5)
        r = servicos.aplicar_importacao(dados, linhas, servicos.MODO_PULAR, "ana")
        self.assertEqual(r["pulados"], 2)

    def test_sem_coluna_de_nome(self):
        df = servicos.ler_planilha(b"a;b\n1;2\n", "x.csv")
        with self.assertRaises(ValueError):
            servicos.preparar_importacao(df)

    def test_excel(self):
        import io
        import pandas as pd
        buf = io.BytesIO()
        pd.DataFrame({"Produto": ["SSD"], "Quantidade": [7]}).to_excel(buf, index=False)
        linhas, erros = servicos.preparar_importacao(servicos.ler_planilha(buf.getvalue(), "a.xlsx"))
        self.assertEqual((linhas[0]["nome"], linhas[0]["estoque"], erros), ("SSD", 7, []))


class TestRelatorios(unittest.TestCase):
    def test_reposicao(self):
        f = filiais_exemplo()
        f["Embu"]["produtos"]["HDMI"] = ItemTI("HDMI", "Cabos", 1, 2)
        df = servicos.itens_para_repor(f, ["Matriz", "Embu"])
        self.assertEqual(list(df["Equipamento"]), ["NOTEBOOK", "HDMI"])  # zerado primeiro
        self.assertEqual(list(df["Sugestão de compra"]), [2, 3])
        self.assertIn("*Embu*", servicos.texto_reposicao(df))
        self.assertTrue(servicos.itens_para_repor({"A": {"produtos": {}, "historico": []}}, ["A"]).empty)

    def test_analises(self):
        h = []
        f = {"produtos": {"MOUSE": ItemTI("MOUSE", "P", 20)}, "historico": h}
        servicos.movimentar(f, "MOUSE", "entrada", 5, "ana")
        servicos.movimentar(f, "MOUSE", "saida", 3, "ana", destino="TI")
        mes = servicos.movimentacao_por_mes(h)
        self.assertEqual(list(mes.iloc[0]), [5, 3])
        self.assertEqual(servicos.top_saidas(h).to_dict(), {"MOUSE": 3})
        vazio = servicos.movimentacao_por_mes([])
        self.assertTrue(vazio.empty)
        df = servicos.historico_df(h)
        hoje = datetime.now().date()
        self.assertEqual(len(servicos.filtrar_historico(df, hoje, hoje)), 2)
        self.assertEqual(len(servicos.filtrar_historico(df, hoje + timedelta(days=1))), 0)
        self.assertEqual(len(servicos.filtrar_historico(df, operacoes=["📤 Saída"])), 1)

    def test_tabela_por_filial(self):
        t = servicos.tabela_por_filial(filiais_exemplo(), ["Matriz", "Embu"])
        self.assertEqual(int(t.loc[t["Equipamento"] == "MOUSE", "Total"].iloc[0]), 5)
        self.assertTrue(servicos.tabela_por_filial({"A": {"produtos": {}, "historico": []}}, ["A"]).empty)


class TestSeguranca(unittest.TestCase):
    def test_login_e_bloqueio(self):
        u = {"ana": seguranca.novo_usuario("Ana", config.PERFIL_OPERADOR, ["Embu"], "senha1234")}
        self.assertEqual(seguranca.verificar_login(u, "ANA ", "senha1234")[0], "ok")
        for _ in range(config.MAX_TENTATIVAS):
            self.assertEqual(seguranca.verificar_login(u, "ana", "errada")[0], "invalido")
        self.assertEqual(seguranca.verificar_login(u, "ana", "senha1234")[0], "bloqueado")
        depois = datetime.now() + timedelta(minutes=config.BLOQUEIO_MINUTOS + 1)
        self.assertEqual(seguranca.verificar_login(u, "ana", "senha1234", depois)[0], "ok")
        self.assertEqual(seguranca.verificar_login(u, "ninguem", "x")[0], "invalido")

    def test_sessao(self):
        u = {"ana": seguranca.novo_usuario("Ana", config.PERFIL_OPERADOR, ["Embu"], "senha1234")}
        s = {}
        token = seguranca.criar_sessao(s, "ana")
        self.assertNotIn(token, str(s))  # só o hash fica guardado
        self.assertEqual(seguranca.validar_sessao(token, u, s), "ana")
        self.assertIsNone(seguranca.validar_sessao("outro", u, s))
        self.assertIsNone(seguranca.validar_sessao(token, u, s, datetime.now() + timedelta(hours=config.SESSAO_HORAS + 1)))
        u["ana"]["ativo"] = False
        self.assertIsNone(seguranca.validar_sessao(token, u, s))
        u["ana"]["ativo"] = True
        seguranca.encerrar_sessao(token, s)
        self.assertIsNone(seguranca.validar_sessao(token, u, s))


class TestArmazenamento(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.orig = (config.ARQUIVO_DADOS, config.ARQUIVO_USUARIOS, config.ARQUIVO_SESSOES, config.PASTA_BACKUP)
        config.ARQUIVO_DADOS = self.tmp / "estoque_ti.json"
        config.ARQUIVO_USUARIOS = self.tmp / "usuarios_ti.json"
        config.ARQUIVO_SESSOES = self.tmp / "sessoes_ti.json"
        config.PASTA_BACKUP = self.tmp / "backups"

    def tearDown(self):
        (config.ARQUIVO_DADOS, config.ARQUIVO_USUARIOS, config.ARQUIVO_SESSOES, config.PASTA_BACKUP) = self.orig

    def test_ida_e_volta_com_series(self):
        f = filiais_exemplo()
        servicos.movimentar(f["Matriz"], "NOTEBOOK", "entrada", 0, "ana", series="A1,A2")
        armazenamento.salvar_dados(f)
        g = armazenamento.carregar_dados()
        self.assertEqual(g["Matriz"]["produtos"]["NOTEBOOK"].series_em_estoque(), ["A1", "A2"])
        self.assertEqual(g["Matriz"]["produtos"]["MOUSE"].estoque_atual, 5)
        self.assertEqual(len(g["Matriz"]["historico"]), 1)

    def test_formato_antigo_e_nome_legado(self):
        config.ARQUIVO_DADOS.write_text(
            '{"produtos":[{"nome":"CABO DE ENERGIA 20 A (PELO MENOS 5)","categoria":"Periféricos",'
            '"estoque_atual":5,"estoque_minimo":2}],"historico":[{"Equipamento":"X"}]}', encoding="utf-8")
        g = armazenamento.carregar_dados()
        item = g["Matriz"]["produtos"]["CABO DE ENERGIA 20 A"]
        self.assertEqual((item.estoque_minimo, item.estoque_atual), (5, 5))
        self.assertEqual(len(g["Matriz"]["historico"]), 1)

    def test_arquivo_corrompido(self):
        config.ARQUIVO_DADOS.write_text("{quebrado", encoding="utf-8")
        with self.assertRaises(armazenamento.ErroArquivo):
            armazenamento.carregar_dados()

    def test_backup_e_zip(self):
        armazenamento.salvar_dados(filiais_exemplo())   # 1º salvamento: ainda não há o que copiar
        armazenamento.salvar_dados(filiais_exemplo())   # 2º: copia o estado anterior
        self.assertEqual(len(armazenamento.listar_backups()), 1)
        antigo = config.PASTA_BACKUP / "estoque_ti_2020-01-01.json"
        antigo.write_text("{}", encoding="utf-8")
        armazenamento.backup_diario()
        self.assertFalse(antigo.exists())  # mais de 30 dias: apagado
        self.assertGreater(len(armazenamento.gerar_zip_backup()), 100)


class TestTransferenciaEmLote(unittest.TestCase):
    def _filiais(self):
        f = filiais_exemplo()
        servicos.movimentar(f["Matriz"], "NOTEBOOK", "entrada", 0, "ana", series="A1,A2,A3")
        return f

    def test_lote_com_protocolo_e_comprovante(self):
        f = self._filiais()
        itens = [{"equipamento": "MOUSE", "quantidade": 2, "series": []},
                 {"equipamento": "NOTEBOOK", "quantidade": 0, "series": ["A1", "A2"]}]
        ok, msg, c = servicos.transferir_lote(f, "Matriz", "Embu", itens, "ana", "Ana Souza", "maria.embu", "Maria Lima")
        self.assertTrue(ok, msg)
        self.assertEqual(c["recebedor"], "Maria Lima (maria.embu)")
        self.assertTrue(c["protocolo"].startswith("TR-"))
        self.assertEqual([i["quantidade"] for i in c["itens"]], [2, 2])
        self.assertEqual(c["usuario_nome"], "Ana Souza")
        self.assertEqual(f["Matriz"]["produtos"]["MOUSE"].estoque_atual, 3)
        self.assertEqual(f["Embu"]["produtos"]["NOTEBOOK"].series_em_estoque(), ["A1", "A2"])
        h = f["Matriz"]["historico"][-2:]
        self.assertTrue(all(c["protocolo"] in x["Detalhes"] and x["Data/Hora"] == c["data_hora"] for x in h))

    def test_tudo_ou_nada(self):
        f = self._filiais()
        itens = [{"equipamento": "MOUSE", "quantidade": 2, "series": []},
                 {"equipamento": "NOTEBOOK", "quantidade": 0, "series": ["A1", "Z9"]}]
        ok, msg, c = servicos.transferir_lote(f, "Matriz", "Embu", itens, "ana")
        self.assertFalse(ok)
        self.assertIsNone(c)
        self.assertEqual(f["Matriz"]["produtos"]["MOUSE"].estoque_atual, 5)
        self.assertEqual(f["Embu"]["produtos"], {})
        # o mesmo produto duas vezes na lista soma e respeita o estoque
        itens = [{"equipamento": "MOUSE", "quantidade": 3, "series": []},
                 {"equipamento": "MOUSE", "quantidade": 3, "series": []}]
        self.assertFalse(servicos.transferir_lote(f, "Matriz", "Embu", itens, "ana")[0])
        self.assertFalse(servicos.transferir_lote(f, "Matriz", "Embu", [], "ana")[0])

    def test_relatorio_sem_duplicar_e_com_nomes(self):
        f = self._filiais()
        itens = [{"equipamento": "MOUSE", "quantidade": 2, "series": []},
                 {"equipamento": "NOTEBOOK", "quantidade": 0, "series": ["A1"]}]
        _, _, c = servicos.transferir_lote(f, "Matriz", "Embu", itens, "ana", "Ana Souza", "maria.embu", "Maria Lima")
        df = servicos.df_transferencias(f, ["Matriz", "Embu"], {"ana": "Ana Souza"})
        self.assertEqual(len(df), 2)  # saída na origem + entrada no destino = 1 linha por produto
        self.assertEqual(set(df["Protocolo"]), {c["protocolo"]})
        self.assertEqual(set(df["Origem"]), {"Matriz"})
        self.assertEqual(set(df["Destino"]), {"Embu"})
        self.assertEqual(df["Enviado por"].iloc[0], "Ana Souza (ana)")
        self.assertEqual(set(df["Recebido por"]), {"Maria Lima (maria.embu)"})
        self.assertIn("A1", set(df["Nº de série"]))
        # quem só enxerga o destino também vê a transferência recebida
        self.assertEqual(len(servicos.df_transferencias(f, ["Embu"])), 2)
        self.assertTrue(servicos.df_transferencias(filiais_exemplo(), ["Matriz"]).empty)

    def test_pdfs(self):
        from nucleo import relatorios
        f = self._filiais()
        _, _, c = servicos.transferir_lote(
            f, "Matriz", "Embu", [{"equipamento": "NOTEBOOK", "quantidade": 0, "series": ["A1"]}], "ana", "Ana ✅ Souza", "maria.embu", "Maria Lima")
        self.assertTrue(relatorios.pdf_comprovante(c).startswith(b"%PDF"))
        df = servicos.df_transferencias(f, ["Matriz", "Embu"]).drop(columns="_data")
        self.assertTrue(relatorios.pdf_relatorio_transferencias(df, "Período: teste").startswith(b"%PDF"))
        vazio = servicos.df_transferencias(filiais_exemplo(), ["Matriz"]).drop(columns="_data")
        self.assertTrue(relatorios.pdf_relatorio_transferencias(vazio).startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
