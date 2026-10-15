"""
Serializadores para la app Inventario y Parámetros de Stock.
"""
from rest_framework import serializers
from .models import GrupoSanguineo, ParametroStockMinimo, EjemplarBolsa

class GrupoSanguineoSerializer(serializers.ModelSerializer):
    idGrupo = serializers.IntegerField(source='idgrupo', read_only=True)
    grupoABO = serializers.CharField(source='grupoabo', read_only=True)
    factorRh = serializers.CharField(source='factorrh', read_only=True)
    tipificacion = serializers.CharField(read_only=True)

    class Meta:
        model = GrupoSanguineo
        fields = ['idgrupo', 'grupoabo', 'factorrh', 'idGrupo', 'grupoABO', 'factorRh', 'tipificacion']


class ParametroStockMinimoSerializer(serializers.ModelSerializer):
    idParametro = serializers.IntegerField(source='idparametro', read_only=True)
    idGrupo = serializers.IntegerField(source='idgrupo.idgrupo', read_only=True)
    tipificacion = serializers.CharField(source='idgrupo.tipificacion', read_only=True)
    grupoABO = serializers.CharField(source='idgrupo.grupoabo', read_only=True)
    factorRh = serializers.CharField(source='idgrupo.factorrh', read_only=True)
    tipoComponente = serializers.CharField(source='tipocomponente', read_only=True)
    stockMinimoSeguridad = serializers.IntegerField(source='stockminimoseguridad', read_only=True)
    stockCriticoAlerta = serializers.IntegerField(source='stockcriticoalerta', read_only=True)
    categoriaEtaria = serializers.CharField(source='categoriaetaria', read_only=True)

    class Meta:
        model = ParametroStockMinimo
        fields = [
            'idparametro',
            'idParametro',
            'idGrupo',
            'tipificacion',
            'grupoABO',
            'factorRh',
            'tipocomponente',
            'tipoComponente',
            'stockminimoseguridad',
            'stockMinimoSeguridad',
            'stockcriticoalerta',
            'stockCriticoAlerta',
            'categoriaetaria',
            'categoriaEtaria',
        ]
        read_only_fields = ['idparametro', 'idParametro', 'idGrupo', 'tipocomponente', 'tipoComponente']


class ParametroStockMinimoUpdateSerializer(serializers.ModelSerializer):
    """
    Serializador para actualizar umbrales de stock mínimo y crítico (PUT /api/stock/parametros/<id>/).
    """
    stockMinimoSeguridad = serializers.IntegerField(source='stockminimoseguridad', required=False)
    stockCriticoAlerta = serializers.IntegerField(source='stockcriticoalerta', required=False)

    class Meta:
        model = ParametroStockMinimo
        fields = ['stockminimoseguridad', 'stockcriticoalerta', 'stockMinimoSeguridad', 'stockCriticoAlerta']

    def validate(self, attrs):
        stock_minimo = attrs.get('stockminimoseguridad', getattr(self.instance, 'stockminimoseguridad', 0))
        stock_critico = attrs.get('stockcriticoalerta', getattr(self.instance, 'stockcriticoalerta', 0))

        if stock_critico < 0 or stock_minimo <= 0 or stock_critico >= stock_minimo:
            raise serializers.ValidationError({
                "stockCriticoAlerta": "El umbral crítico debe ser no negativo y menor que el mínimo de seguridad."
            })

        return attrs


class StockAlertaSerializer(serializers.Serializer):
    idParametro = serializers.IntegerField()
    idGrupo = serializers.IntegerField()
    tipificacion = serializers.CharField()
    tipoComponente = serializers.CharField()
    stockMinimoSeguridad = serializers.IntegerField()
    stockCriticoAlerta = serializers.IntegerField()
    stockDisponibleActual = serializers.IntegerField()
    deficitUnidades = serializers.IntegerField()
    nivelAlerta = serializers.CharField()
    requiereCampanaDonacion = serializers.BooleanField()
