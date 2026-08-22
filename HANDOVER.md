# Handover — Catan Opening Advisor

Stato al 23 agosto 2026. Ultimo commit: `8e50030`. 179 test verdi, tutto pushato
su https://github.com/Dalamar90/catan-opening-advisor

---

## Dove siamo

| Milestone | Stato |
|---|---|
| M1 — modello, geometria, pre-calcolo §B.6 | fatto |
| M2 — punteggio `S(v)` del singolo incrocio | fatto |
| M3 — valutazione della coppia | fatto |
| M4 — draft, avversari, mercato, strade | fatto |
| M5 — output spiegabile §D.3 | fatto |
| M6 — validazione su Catanatron | **non iniziato** |

In più, fuori piano: lettura del tabellone da foto (funziona, ma la fa il modello
in chat, non il codice) e output HTML col tabellone disegnato.

## Come si usa

```bash
pip install -e ".[dev]"
python -m catan_advisor.cli advise boards/mio.json --position 3
python -m catan_advisor.cli advise boards/mio.json --html apertura.html
```

Altri comandi, uno per livello del modello: `newboard`, `validate`, `map`,
`precompute` (§B.6), `score` (§B.3), `pair` (§B.4), `draft` (§C).
`score --explain v26` e `pair --explain v18,v26` stampano il breakdown completo.

## Le tre cose da sapere prima di toccare il codice

1. **Ogni punteggio è una lista di contributi etichettati, non un float.** La
   somma dei contributi *è* il punteggio, e c'è un test che lo verifica. Le
   motivazioni nell'output sono estratte da lì: cambiare un peso in
   `config.yaml` cambia anche la spiegazione. Non aggiungere mai testo
   esplicativo scritto a mano — divergerebbe dal calcolo al primo ritocco.
2. **Regole in `constants.py`, opinioni in `config.yaml`.** Se un numero è una
   regola di Catan sta nel codice; se è una nostra stima sta nella config.
3. **I termini di portafoglio si calcolano una volta sola, nella coppia.**
   Varietà, porti, espansione, ladro: `score_vertex(standalone=False)` li
   esclude apposta. Un test fallisce se ricompaiono dentro un membro.

## Correzioni alla KB già fatte (non rifarle)

- **Catanatron è GPL-3.0-or-later, non MIT.** Da qui la licenza GPL della repo.
- **L'espansione "a 1 strada" di §B.3 è impossibile**: un incrocio a una strada
  è adiacente alla colonia, la distance rule lo vieta per sempre. Il primo
  bersaglio edificabile è a distanza 2.
- **Coefficienti espansione ricalibrati** (0.11/0.045 → 0.08/0.032): con i
  valori della KB il 76% e l'84% degli incroci finiva al tetto.
- **Il malus ladro di §B.3 non può scattare** su setup bilanciato: le tre
  tessere di un incrocio sono mutuamente adiacenti e 6/8 non si toccano, quindi
  il massimo è 5 contro una soglia di 10. Spostato a livello di coppia.
- **La copertura risorse non è binaria**: §B.4 pagherebbe +4 pieni per una
  risorsa coperta da un solo 12. Ora il credito cresce con la produzione.
- **L'erosione di §C.1 (2.5 incroci per pick) sottostima**: la simulazione ne
  conta ~4, perché una colonia brucia sé stessa più fino a tre vicini.

## Bug noto, da correggere per primo

**La penalità per vincolo hard violato è fissa** (`-3.0`), quindi "grano 0" e
"grano 3" pesano uguale. In una partita reale questo ha portato il motore a
mettere primo un incrocio da 23 pip con **zero grano** su uno da 21 con 5/5
risorse — consiglio che l'utente ha giustamente scartato. Serve una penalità
proporzionale a quanto si è sotto soglia. Sta in
`catan_advisor/scoring/pair.py`, funzione `_add_hard_constraints`.

## Altri debiti aperti

- `load_config` è `lru_cache`d: modificare `config.yaml` a processo vivo non ha
  effetto. Fastidioso durante la calibrazione.
- L'indice di concentrazione spaziale è rumoroso su 3 tessere; la soglia 0.15 è
  inventata.
- `Board` è un dataclass mutabile con `cached_property`: andrebbe congelato.
- Il parser dell'input abbreviato (§D.1) non è mai stato scritto. Valutato con
  l'utente e **scartato**: scrivere a mano non è più veloce di una foto.

## M6 — dove si è fermato

La geometria combacia: la mappatura fra i 54 incroci nostri e i 54 nodi di
Catanatron è una **biiezione perfetta, zero conflitti**, verificata. Il codice
per ricostruirla:

```python
# cubo (x, y, z) -> assiale (q, r) = (x, z)
# corners_of() restituisce [SE, S, SO, NO, N, NE], che si allinea a NodeRef
CORNER_ORDER = ["SOUTHEAST", "SOUTH", "SOUTHWEST", "NORTHWEST", "NORTH", "NORTHEAST"]
```

**Il blocco**: il pacchetto PyPI `catanatron` 3.2.1 è una versione ridotta, senza
`catanatron.features` e senza `ValueFunctionPlayer` — cioè senza l'avversario
forte contro cui volevamo misurarci. Quello sta solo su GitHub, e
`pip install git+...#subdirectory=catanatron` fallisce perché il `pyproject.toml`
è nella root del monorepo, non nel sottopacchetto.

Tre strade, in ordine di preferenza: clonare il repo e installarlo a mano;
copiare il solo `value.py` (194 righe) in `validation/` con attribuzione GPL;
rinunciare e misurarsi contro i bot deboli (inutile).

Il target resta: win rate > 25% a 4 giocatori con significatività statistica.

## Come lavorare con l'utente

- **Durante una partita: tre righe.** Dove piazzare, la strada, un motivo.
  Niente tabelle, niente confronto fra opzioni, niente pagina HTML se non la
  chiede. Il dettaglio esiste già nei comandi, si offre solo su richiesta.
- **Identifica le colonie dalle tre tessere che toccano, mai dai pixel.** Il
  matching per posizione ha sbagliato due volte su tre e ogni errore è costato
  un giro di correzione. `{h15, h18, h19}` ha una sola soluzione su tutto il
  tabellone.
- **Chiedi il colore prima di calcolare**, non dopo.
- Il tabellone si inserisce una volta per partita; ai turni successivi si
  aggiornano solo i `placements`.
- Niente dati della sua sessione BGA, link di partita o screenshot nella repo.

## Filo aperto: leggere BGA direttamente

L'utente gioca su Board Game Arena. BGA tiene lo stato della partita in una
variabile della pagina, quindi in linea di principio si legge in modo esatto
senza foto — che eliminerebbe l'unico vero collo di bottiglia.

Serve l'estensione Claude in Chrome (non installata al momento
dell'handover) e uno script **locale, fuori dalla repo**. Non verificato: non
sappiamo ancora se quella variabile contenga il tabellone in forma utilizzabile.
Da provare aprendo una partita e guardando, cinque minuti.

## La domanda ancora senza risposta

Nessuno ha mai misurato se questi consigli fanno vincere. Ogni numero in
`config.yaml` è una stima ragionata. Tre stime della KB si sono rivelate
sbagliate semplicemente scrivendo i test; un peso *tarato male* non si vede
guardandolo, serve M6.
