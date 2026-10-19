# HSL-vyöhykekartta

Kartta HSL:n maksuvyöhykkeistä A–E ja haku lähimmälle pysäkille, jolta oma lippu kelpaa.

- `index.html` – itse kartta (avautuu myös suoraan tiedostona).
- `data/` – vyöhykkeet, pysäkit, hinnat ja aineiston päivämäärä. Generoitu, älä muokkaa käsin.
- `tools/update.py` – lataa HSL:n uusimman vyöhyketason ja GTFS-aineiston ja ajaa `prep.py`:n.
- `tools/prep.py` – muuntaa ladatun aineiston `data/`-kansioon.
- `.github/workflows/update-data.yml` – ajaa päivityksen maanantaisin ja julkaisee sivun GitHub Pagesiin.

Päivitys käsin: `python -I tools/update.py` (tarvitsee numpyn).

Lähteet: HSL:n maksuvyöhykkeet (CC BY 4.0, HSL), HSL GTFS, pohjakartta Esri / OpenStreetMap,
kävelyreitit OSRM (FOSSGIS), osoitehaku Photon.
