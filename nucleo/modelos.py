"""Modelo de dados: um item de estoque de T.I."""
from . import config


class ItemTI:
    def __init__(
        self,
        nome,
        categoria,
        estoque_atual=0,
        estoque_minimo=2,
        controla_serie=False,
        unidades=None,
    ):
        self.nome = nome.upper().strip()
        self.categoria = categoria.strip()
        self.estoque_atual = int(estoque_atual)
        self.estoque_minimo = int(estoque_minimo)
        self.controla_serie = bool(controla_serie)
        # {numero_de_serie: {"situacao": "Em estoque"|"Saiu", "destino": str, "data": str}}
        self.unidades = dict(unidades or {})
        if self.controla_serie:
            self.sincronizar_estoque()

    @property
    def status(self):
        if self.estoque_atual <= 0:
            return config.STATUS_CRITICO
        if self.estoque_atual <= self.estoque_minimo:
            return config.STATUS_ALERTA
        return config.STATUS_OK

    def series_em_estoque(self):
        return sorted(
            s for s, u in self.unidades.items() if u.get("situacao") == config.EM_ESTOQUE
        )

    def sincronizar_estoque(self):
        """Em itens com número de série, o estoque é a contagem das unidades em estoque."""
        if self.controla_serie:
            self.estoque_atual = len(self.series_em_estoque())

    def to_dict(self):
        d = {
            "nome": self.nome,
            "categoria": self.categoria,
            "estoque_atual": self.estoque_atual,
            "estoque_minimo": self.estoque_minimo,
        }
        if self.controla_serie:
            d["controla_serie"] = True
            d["unidades"] = self.unidades
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(
            d["nome"],
            d.get("categoria", "Sem categoria"),
            d.get("estoque_atual", 0),
            d.get("estoque_minimo", 2),
            d.get("controla_serie", False),
            d.get("unidades"),
        )
