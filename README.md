# Catan Opening Advisor

Consigliere per la **fase di apertura** di Catan (gioco base, 3-4 giocatori): dove
piazzare le due colonie iniziali e le due strade, **con la spiegazione del perché**.

Non gioca al posto tuo e non implementa il mid-game. La specifica completa è in
[`catan-opening-advisor-kb.md`](catan-opening-advisor-kb.md).

## Principi di progetto

1. **Niente MCTS, niente reti neurali.** Una funzione di valutazione pesata e
   interpretabile (KB §E.5).
2. **La spiegabilità è il requisito numero uno.** Ogni punteggio deve saper dire
   da dove viene.
3. **Il contatore di pip resta sempre visibile** accanto al punteggio pesato: il
   punteggio è l'opinione del modello, i pip sono il fatto che puoi verificare a
   occhio al tavolo.
4. **Regole in `constants.py`, opinioni in `config.yaml`.** Se un numero è una
   regola di Catan sta nel codice; se è una nostra stima sta nella config, dove
   la calibrazione potrà riscriverlo.

## Stato

| Milestone | Contenuto | Stato |
|---|---|---|
| M1 | Modello del tabellone, geometria, pre-calcolo §B.6 | ✅ fatto |
| M2 | Valutazione del singolo incrocio `S(v)` | da fare |
| M3 | Valutazione della coppia (il cuore) | da fare |
| M4 | Contesto di draft, avversari, strade | da fare |
| M5 | Output spiegabile §D.3 | da fare |
| M6 | Validazione su Catanatron | da fare |

## Uso

```bash
pip install -e ".[dev]"

# genera un tabellone casuale legale
python -m catan_advisor.cli newboard --seed 7 -o boards/mio.json

# controlla che un tabellone sia legale (utile dopo la lettura da foto)
python -m catan_advisor.cli validate boards/mio.json

# il tabellone in righe 3-4-5-4-3, per confrontarlo con la foto
python -m catan_advisor.cli map boards/mio.json

# il pre-calcolo obbligatorio della KB §B.6
python -m catan_advisor.cli precompute boards/mio.json --players 4 --position 2
```

## Come si inserisce un tabellone

L'inserimento a mano di 19 tessere è il collo di bottiglia noto (KB §E.8). Il
flusso previsto è:

1. fotografi il tabellone;
2. la foto viene letta e trasformata nel JSON di §D.1;
3. `validate` verifica che il risultato sia un tabellone **legale** — 19 tessere,
   i conteggi di terreno giusti, il multiset esatto dei 18 gettoni, 58 pip
   totali. Una lettura sbagliata quasi sempre rompe uno di questi vincoli, quindi
   l'errore salta fuori subito invece di inquinare i consigli;
4. `map` stampa il tabellone in righe 3-4-5-4-3 per il confronto visivo finale.

Gli id seguono l'ordine di lettura: `h01`-`h19` da nord a sud e da ovest a est,
`v01`-`v54` e `e01`-`e72` con lo stesso criterio.

## Geometria

I 54 incroci e i 72 lati sono derivati analiticamente dalle coordinate assiali
dei 19 esagoni pointy-top. Un vertice **è** l'insieme delle tre posizioni di
esagono che lo toccano (alcune possono essere mare), quindi la sua identità è
esatta e non serve alcuna tolleranza in floating point. Il matching per pixel
resta la strada giusta per il futuro parser fotografico, dove le coordinate sono
davvero rumorose.

## Test

```bash
python -m pytest -q
```

## Licenza

**GPL-3.0-or-later** — vedi [`LICENSE`](LICENSE).

La scelta è dettata da M6: [Catanatron](https://github.com/bcollazo/catanatron),
che useremo per la validazione, è a sua volta GPL-3.0-or-later (non MIT, come
diceva la prima stesura della KB). Un `Player` custom che eredita dalle sue classi
è un import in-process di codice GPL, quindi licenziare tutto GPL toglie ogni
ambiguità. Catanatron resta comunque una dipendenza opzionale, installata
dall'utente e usata solo da `validation/`: il motore non la importa mai.

Progetto non affiliato a Catan GmbH; *Catan* è un loro marchio registrato.
