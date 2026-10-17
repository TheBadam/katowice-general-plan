<?xml version="1.0" encoding="UTF-8"?>
<mpzp:PlanZagospodarowania
    xmlns:gml="http://www.opengis.net/gml/3.2"
    xmlns:mpzp="urn:example:mpzp-przyklad"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">

  <gml:boundedBy>
    <gml:Envelope srsName="urn:ogc:def:crs:EPSG::2177" srsDimension="2">
      <gml:lowerCorner>5561000 6515000</gml:lowerCorner>
      <gml:upperCorner>5563200 6519400</gml:upperCorner>
    </gml:Envelope>
  </gml:boundedBy>

  <!-- Plan boundary -->
  <gml:featureMember>
    <mpzp:GranicaPlanu>
      <mpzp:idPlanu>MPZP-KAT-001</mpzp:idPlanu>
      <mpzp:nazwaPlanu>Przykładowy plan - fragment (dane syntetyczne)</mpzp:nazwaPlanu>
      <mpzp:geometria>
        <gml:Polygon srsName="urn:ogc:def:crs:EPSG::2177">
          <gml:exterior>
            <gml:LinearRing>
              <gml:posList srsDimension="2">
                5561000 6515000 5563200 6515000 5563200 6519400
                5561800 6519400 5561000 6517800 5561000 6515000
              </gml:posList>
            </gml:LinearRing>
          </gml:exterior>
        </gml:Polygon>
      </mpzp:geometria>
    </mpzp:GranicaPlanu>
  </gml:featureMember>

  <!-- Planned functions (zones) -->
  <gml:featureMember>
    <mpzp:FunkcjeMP>
      <mpzp:idZespolu>1</mpzp:idZespolu>
      <mpzp:funkcjaSymbol>ZM</mpzp:funkcjaSymbol>
      <mpzp:funkcjaNazwa>Zabudowa mieszkaniowa</mpzp:funkcjaNazwa>
      <mpzp:geometria>
        <gml:MultiSurface srsName="urn:ogc:def:crs:EPSG::2177">
          <gml:surfaceMember>
            <gml:Polygon>
              <gml:exterior>
                <gml:LinearRing>
                  <gml:posList>
                    5562900 6515100 5563100 6515100 5563100 6517800 5562900 6517800 5562900 6515100
                  </gml:posList>
                </gml:LinearRing>
              </gml:exterior>
            </gml:Polygon>
          </gml:surfaceMember>
          <gml:surfaceMember>
            <gml:Polygon>
              <gml:exterior>
                <gml:LinearRing>
                  <gml:posList>
                    5562500 6515300 5562900 6515300 5562900 6516400 5562500 6516400 5562500 6515300
                  </gml:posList>
                </gml:LinearRing>
              </gml:exterior>
            </gml:Polygon>
          </gml:surfaceMember>
        </gml:MultiSurface>
      </mpzp:geometria>
    </mpzp:FunkcjeMP>
  </gml:featureMember>

  <gml:featureMember>
    <mpzp:FunkcjeMP>
      <mpzp:idZespolu>2</mpzp:idZespolu>
      <mpzp:funkcjaSymbol>ZL</mpzp:funkcjaSymbol>
      <mpzp:funkcjaNazwa>Zieleń leśna</mpzp:funkcjaNazwa>
      <mpzp:geometria>
        <gml:Polygon srsName="urn:ogc:def:crs:EPSG::2177">
          <gml:exterior>
            <gml:LinearRing>
              <gml:posList>
                5561200 6515100 5562500 6515100 5562500 6517000 5561200 6517000 5561200 6515100
              </gml:posList>
            </gml:LinearRing>
          </gml:exterior>
          <gml:interior>
            <gml:LinearRing>
              <gml:posList>
                5561500 6515400 5561900 6515400 5561900 6515900 5561500 6515900 5561500 6515400
              </gml:posList>
            </gml:LinearRing>
          </gml:interior>
        </gml:Polygon>
      </mpzp:geometria>
    </mpzp:FunkcjeMP>
  </gml:featureMember>

  <gml:featureMember>
    <mpzp:FunkcjeMP>
      <mpzp:idZespolu>3</mpzp:idZespolu>
      <mpzp:funkcjaSymbol>ZW</mpzp:funkcjaSymbol>
      <mpzp:funkcjaNazwa>Zabudowa mieszkaniowa z usługami</mpzp:funkcjaNazwa>
      <mpzp:geometria>
        <gml:Polygon srsName="urn:ogc:def:crs:EPSG::2177">
          <gml:exterior>
            <gml:LinearRing>
              <gml:posList>
                5561500 6515400 5561900 6515400 5561900 6515900 5561500 6515900 5561500 6515400
              </gml:posList>
            </gml:LinearRing>
          </gml:exterior>
        </gml:Polygon>
      </mpzp:geometria>
    </mpzp:FunkcjeMP>
  </gml:featureMember>

  <gml:featureMember>
    <mpzp:FunkcjeMP>
      <mpzp:idZespolu>4</mpzp:idZespolu>
      <mpzp:funkcjaSymbol>ZC</mpzp:funkcjaSymbol>
      <mpzp:funkcjaNazwa>Usługi publiczne</mpzp:funkcjaNazwa>
      <mpzp:geometria>
        <gml:Polygon srsName="urn:ogc:def:crs:EPSG::2177">
          <gml:exterior>
            <gml:LinearRing>
              <gml:posList>
                5561200 6517500 5562000 6517500 5562000 6519300 5561200 6519300 5561200 6517500
              </gml:posList>
            </gml:LinearRing>
          </gml:exterior>
        </gml:Polygon>
      </mpzp:geometria>
    </mpzp:FunkcjeMP>
  </gml:featureMember>

  <gml:featureMember>
    <mpzp:FunkcjeMP>
      <mpzp:idZespolu>5</mpzp:idZespolu>
      <mpzp:funkcjaSymbol>ZP</mpzp:funkcjaSymbol>
      <mpzp:funkcjaNazwa>Zieleń urządzona / park</mpzp:funkcjaNazwa>
      <mpzp:geometria>
        <gml:Polygon srsName="urn:ogc:def:crs:EPSG::2177">
          <gml:exterior>
            <gml:LinearRing>
              <gml:posList>
                5562100 6517600 5563100 6517600 5563100 6519300 5562100 6519300 5562100 6517600
              </gml:posList>
            </gml:LinearRing>
          </gml:exterior>
        </gml:Polygon>
      </mpzp:geometria>
    </mpzp:FunkcjeMP>
  </gml:featureMember>

  <!-- Road axes (lines) -->
  <gml:featureMember>
    <mpzp:LinieMP>
      <mpzp:idLini>10</mpzp:idLini>
      <mpzp:nazwaLini>ul. Przykładowa - oś ulicy</mpzp:nazwaLini>
      <mpzp:geometria>
        <gml:LineString srsName="urn:ogc:def:crs:EPSG::2177">
          <gml:posList>
            5561000 6516600 5561900 6516600 5563200 6517300
          </gml:posList>
        </gml:LineString>
      </mpzp:geometria>
    </mpzp:LinieMP>
  </gml:featureMember>

  <gml:featureMember>
    <mpzp:LinieMP>
      <mpzp:idLini>11</mpzp:idLini>
      <mpzp:nazwaLini>ul. Plenerowa - oś ulicy</mpzp:nazwaLini>
      <mpzp:geometria>
        <gml:LineString srsName="urn:ogc:def:crs:EPSG::2177">
          <gml:posList>
            5562500 6515100 5562500 6519400
          </gml:posList>
        </gml:LineString>
      </mpzp:geometria>
    </mpzp:LinieMP>
  </gml:featureMember>

  <!-- Line with no attributes (tests attribute-less features) -->
  <gml:featureMember>
    <mpzp:LinieZabudowy>
      <mpzp:geometria>
        <gml:LineString srsName="urn:ogc:def:crs:EPSG::2177">
          <gml:posList>
            5562600 6515300 5562600 6517400
          </gml:posList>
        </gml:LineString>
      </mpzp:geometria>
    </mpzp:LinieZabudowy>
  </gml:featureMember>

  <!-- Plan symbols (points) -->
  <gml:featureMember>
    <mpzp:PunktyMP>
      <mpzp:idPunktu>21</mpzp:idPunktu>
      <mpzp:symbol>PP</mpzp:symbol>
      <mpzp:opis>Punkt poboru wody</mpzp:opis>
      <mpzp:geometria>
        <gml:Point srsName="urn:ogc:def:crs:EPSG::2177">
          <gml:pos>5563050 6517350</gml:pos>
        </gml:Point>
      </mpzp:geometria>
    </mpzp:PunktyMP>
  </gml:featureMember>

  <gml:featureMember>
    <mpzp:PunktyMP>
      <mpzp:idPunktu>22</mpzp:idPunktu>
      <mpzp:symbol>KP</mpzp:symbol>
      <mpzp:opis>Kluczowy punkt pomiarowy</mpzp:opis>
      <mpzp:geometria>
        <gml:Point srsName="urn:ogc:def:crs:EPSG::2177">
          <gml:pos>5561500 6519100</gml:pos>
        </gml:Point>
      </mpzp:geometria>
    </mpzp:PunktyMP>
  </gml:featureMember>

</mpzp:PlanZagospodarowania>
