# Catan — Knowledge Base per Advisor di Apertura

**Scope:** Catan base (senza espansioni), 3 e 4 giocatori.
**Obiettivo:** fornire a un motore di consigli tutte le regole, i numeri e le euristiche necessarie per scegliere le **due colonie iniziali e le due strade iniziali**, tenendo conto di: probabilità, risorse, porti, posizione nell'ordine di piazzamento, e piazzamenti già fatti dagli avversari.

Questo documento è pensato per essere letto da un LLM come contesto operativo. È diviso in:
- **Parte A — Fatti** (regole, costanti, matematica): non negoziabile, va trattato come verità.
- **Parte B — Modello di valutazione** (formule e pesi): implementabile, calibrabile.
- **Parte C — Strategia contestuale** (draft, avversari, archetipi): ragionamento.
- **Parte D — Implementazione** (schema dati, pseudocodice, output atteso).

---

# PARTE A — FATTI E COSTANTI

## A.1 Composizione del tabellone base

| Terreno | Risorsa | N° tessere |
|---|---|---|
| Foresta | Legno (wood) | 4 |
| Campo | Grano (wheat) | 4 |
| Pascolo | Pecora (sheep) | 4 |
| Collina | Mattone (brick) | 3 |
| Montagna | Minerale (ore) | 3 |
| Deserto | — | 1 |
| **Totale** | | **19** |

**Conseguenza chiave: mattone e minerale sono strutturalmente scarsi** (3 tessere su 18 produttive ciascuno, ~16.7%). Legno, grano e pecora sono al 22.2%.

Geometria: 19 esagoni → **54 incroci** (vertici) e **72 lati** (edge).

## A.2 Gettoni numerici

18 gettoni: `2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12`

**Pip = numero di combinazioni su 36 con 2d6:**

| Numero | Pip | Probabilità |
|---|---|---|
| 2 | 1 | 2.78% |
| 3 | 2 | 5.56% |
| 4 | 3 | 8.33% |
| 5 | 4 | 11.11% |
| 6 | 5 | 13.89% |
| 7 | 6 | 16.67% (ladro) |
| 8 | 5 | 13.89% |
| 9 | 4 | 11.11% |
| 10 | 3 | 8.33% |
| 11 | 2 | 5.56% |
| 12 | 1 | 2.78% |

**Pip totali sul tabellone = 58.**
Distribuzione per risorsa **non** è uniforme e cambia ad ogni partita: va sempre ricalcolata dal tabellone reale (vedi §B.6).

Regola di setup standard: 6 e 8 non possono essere adiacenti fra loro (nel setup casuale "bilanciato"). Se giocate col setup completamente random, questa regola salta e vanno cercati i cluster.

## A.3 Costi di costruzione

| Costruzione | Costo | Effetto |
|---|---|---|
| Strada | 1 legno + 1 mattone | espansione / strada più lunga |
| Colonia | 1 legno + 1 mattone + 1 grano + 1 pecora | +1 PV, +1 produzione per tessera |
| Città | 2 grano + 3 minerale | +1 PV, raddoppia produzione su 3 tessere |
| Carta sviluppo | 1 grano + 1 pecora + 1 minerale | cavaliere / PV / carte progresso |

**Catene di conversione (fondamentale per l'advisor):**
- **Legno + Mattone** = motore di *espansione* (early game). Coppia 1:1.
- **Grano + Minerale** = motore di *scaling* (mid/late game). Rapporto 2:3.
- **Grano + Pecora + Minerale** = motore di *carte* (esercito più grande, +2 PV; carte punto).
- **Il grano entra in 3 costruzioni su 4.** È la risorsa più universale del gioco.
- **La pecora entra in 2 su 4** ed è abbondante → è la risorsa con minor valore di scambio.

## A.4 Regole rilevanti per l'apertura

- **Distance rule:** una colonia non può essere costruita su un incrocio adiacente a un altro incrocio occupato (serve almeno 1 incrocio vuoto in mezzo). Occupare un incrocio "brucia" i 3 incroci vicini.
- **Ordine serpentina (snake draft):** giocatori 1→N piazzano colonia+strada, poi N→1 piazzano la seconda colonia+strada.
- **La seconda colonia genera risorse iniziali** dalle sue tessere adiacenti (1 carta per tessera produttiva). La prima no.
- **Le strade iniziali** devono partire dalla colonia appena piazzata.
- **Il ladro parte nel deserto.** Con un 7 il ladro si muove, blocca una tessera e ruba una carta; chi ha ≥8 carte scarta metà.
- **Porti:** 4 porti generici 3:1 + 5 porti specifici 2:1 (uno per risorsa). Vanno "attivati" costruendo una colonia su uno dei 2 incroci del porto.
- **Punti vittoria:** 10 per vincere. Colonia 1, Città 2, Strada più lunga (≥5) 2, Esercito più grande (≥3 cavalieri) 2, carte punto 1 ciascuna (5 nel mazzo).

## A.5 Ordine di pick per posizione

**4 giocatori** (8 pick totali):

| Posizione | 1° pick | 2° pick | Pick di attesa |
|---|---|---|---|
| P1 | #1 | #8 | 6 |
| P2 | #2 | #7 | 4 |
| P3 | #3 | #6 | 2 |
| P4 | #4 | #5 | 0 |

**3 giocatori** (6 pick totali):

| Posizione | 1° pick | 2° pick | Pick di attesa |
|---|---|---|---|
| P1 | #1 | #6 | 4 |
| P2 | #2 | #5 | 2 |
| P3 | #3 | #4 | 0 |

Il "pick di attesa" è la variabile più importante per decidere se essere **greedy** (prendo il meglio adesso) o **pianificatore** (costruisco una coppia coerente).

---

# PARTE B — MODELLO DI VALUTAZIONE

## B.1 Valore grezzo di un incrocio (pip score)

```
pip_grezzo(v) = Σ pip(tessera_i)   per le tessere adiacenti a v (max 3)
```

**Benchmark di riferimento (base game):**

| pip grezzo | Giudizio |
|---|---|
| ≥ 12 | Eccezionale (raro) |
| 10–11 | Ottimo — livello top-3 del tabellone |
| 8–9 | Buono |
| 6–7 | Mediocre — accettabile solo con porto o risorse rare |
| ≤ 5 | Scarto |

Note:
- Un incrocio costiero ha spesso solo **2 tessere** → tetto massimo più basso. Va compensato da porto o da risorse rare.
- Un incrocio adiacente al **deserto** è di fatto a 2 tessere, ma con un piccolo vantaggio: il ladro parte lì e la tessera non può essere bloccata contro di te in modo utile.
- **2 e 12 valgono quasi zero** (1 pip). Un incrocio 6-8-2 va letto come "10 pip" ma con solo 2 fonti reali.

## B.2 Pesi delle risorse

Il pip grezzo va corretto per **utilità × scarsità**. Pesi base consigliati (profilo neutro, inizio partita):

```
W_grano    = 1.20
W_minerale = 1.10
W_mattone  = 1.10
W_legno    = 1.00
W_pecora   = 0.80
```

```
pip_pesato(v) = Σ pip(tessera_i) × W(risorsa_i)
```

**Correzione dinamica per scarsità reale del tabellone** — da applicare sempre, perché i tabelloni variano molto:

```
pip_risorsa_r = Σ pip di tutte le tessere di tipo r sul tabellone
quota_r       = pip_risorsa_r / 58
W_finale(r)   = W_base(r) × (quota_attesa_r / quota_r)^0.5

dove quota_attesa: legno .222, grano .222, pecora .222, mattone .167, minerale .167
```

Esempio: se in questa partita il minerale è su 8, 6, 5 (14 pip → quota 0.241 contro 0.167 atteso), il minerale è **abbondante** e il suo peso scende. Se è su 3, 4, 11 (7 pip → 0.121), è **estremamente scarso** e il peso sale: chi lo prende avrà potere di mercato per tutta la partita.

## B.3 Bonus e malus strutturali di un singolo incrocio

```
+ diversità_risorse (⚠ CORRETTO — vedi §E.2):
    +1.5 per risorsa distinta sull'incrocio
    (bonus VOLUTAMENTE basso qui: la diversità è una proprietà del
     PORTAFOGLIO, non del singolo incrocio. Il peso grosso va in §B.4.
     Un incrocio monorisorsa non è un errore se l'altra colonia compensa.)

+ diversità_numerica:
    3 numeri distinti   → +0.5
    numero ripetuto     → −0.8 per ripetizione
    (6-6 o 8-8 sullo stesso incrocio: alto pip ma varianza altissima
     e bersaglio numero uno del ladro)

+ copertura fascia media:
    almeno 2 tessere fra 4,5,6,8,9,10 → +0.5
    solo numeri estremi (2,3,11,12)   → −1.5

+ espansione:
    per ogni incrocio LEGALE raggiungibile con 1 strada e con pip ≥ 8: +0.9  (max +1.8)
    per ogni incrocio legale a 2 strade con pip ≥ 9:                  +0.4  (max +0.8)
    incrocio in vicolo cieco (0 sbocchi utili):                       −1.2

+ porto (vedi §B.5)

− rischio ladro:
    pip su 6/8 dell'incrocio ≥ 10 e incrocio isolato → −0.6
    (sei il bersaglio designato: chiunque tiri 7 ti blocca)
```

**Formula sintetica per incrocio singolo:**

```
S(v) = pip_pesato(v) + Σ bonus − Σ malus
```

## B.4 Valutazione della COPPIA (il vero output)

**Questo è il punto centrale: non si valutano due colonie, si valuta un portafoglio.**

```
S_coppia(A,B) = S(A) + S(B) + sinergia(A,B)
```

### Vincoli hard (se violati → flag rosso, sconsiglia)

| Vincolo | Soglia | Motivo |
|---|---|---|
| Grano combinato | **≥ 4 pip** | senza grano non costruisci colonie, città né carte |
| Risorse coperte | **≥ 4 su 5** (o 4 + porto 2:1 sulla ridondante) | il 5° buco si copre solo con scambi, e sei ostaggio |
| Pip totali coppia | **≥ 18** | sotto questa soglia sei in ritardo strutturale |
| Legno **e** mattone | **≥ 2 pip ciascuno** | senza strade non ti espandi, resti a 2 colonie |

### Bonus di sinergia

```
⚠ VALORI CORRETTI dopo l'ispezione di Catanatron (§E.2).
Ogni risorsa distinta coperta vale ~4 pip-equivalenti. Quindi, in
termini RELATIVI rispetto a una copertura 3/5:

+ copertura 5/5 risorse:                         +8.0
+ copertura 4/5 con porto 2:1 sulla ridondante:  +6.0
+ copertura 4/5 senza compensazione:             +4.0
+ copertura 3/5:                                  0.0  (baseline)
+ copertura 2/5:                                 −4.0

Questo è il singolo cambiamento più importante rispetto alla v1: la
diversità vale MOLTO più di quanto stimato inizialmente. Una coppia da
19 pip con 5/5 risorse batte una coppia da 23 pip con 3/5.

+ bilanciamento legno:mattone entro 1.5:1        +1.0
  (il motore strade funziona solo in coppia)
+ grano ≥ 6 pip                                  +1.0
+ minerale ≥ 5 pip E grano ≥ 5 pip               +1.5  (motore città attivo)

+ diversificazione numerica del portafoglio:
    conta i numeri distinti coperti dalle 2 colonie
    ≥ 5 numeri distinti → +1.0
    ≤ 3 numeri distinti → −1.5  (partita a lotteria)

+ nessun numero singolo pesa > 35% dei pip totali → +0.8
```

### Benchmark coppia

| Pip totali (grezzi) | Giudizio |
|---|---|
| ≥ 22 | Apertura da vincitore |
| 20–21 | Molto forte |
| 18–19 | Solida |
| 16–17 | Sotto media, serve un piano (porto/carte/blocco) |
| ≤ 15 | Apertura persa: pianifica su scambi e strada più lunga |

## B.5 Porti — quando valgono davvero

**Regola d'oro: un porto senza produzione è una casella sprecata.** Gli incroci portuali sono quasi sempre costieri → 2 tessere → pip bassi. Il porto deve *pagare* quella perdita.

### Porto 2:1 specifico

```
valore(porto 2:1 su risorsa r) =
    0                       se pip_coppia(r) < 3
    +1.0                    se pip_coppia(r) = 3–4
    +2.2                    se pip_coppia(r) = 5–7
    +3.2                    se pip_coppia(r) ≥ 8
```

Applicazioni classiche:
- **2:1 pecora + pascoli forti** → motore carte sviluppo. La pecora è la risorsa peggiore da scambiare coi giocatori; il porto la trasforma in valuta. Combo storicamente fortissima.
- **2:1 minerale + montagna su 6/8** → città a raffica.
- **2:1 legno o mattone** → utile solo in strategia strada più lunga con produzione molto sbilanciata.

### Porto 3:1 generico

```
valore(porto 3:1) =
    +0.4    di base
    +1.0    se la coppia ha ≥ 20 pip totali (alta produzione = alto surplus)
    +1.2    se la coppia ha una risorsa con ≥ 8 pip (surplus strutturale)
```

Il 3:1 è un'assicurazione contro il blocco negli scambi e contro giocatori ostili. Vale di più a 4 giocatori che a 3.

### Timing
- **Primo pick: quasi mai un porto.** Costa troppi pip in un momento in cui il tabellone è ancora libero.
- **Secondo pick: il porto è un candidato serio**, perché a quel punto conosci il tuo portafoglio e sai quale ridondanza hai.
- Se il porto rilevante è a 1–2 strade dalla tua colonia, **non prenderlo ora**: prenotalo con la strada iniziale. Il pick va speso sui pip.

## B.6 Pre-calcolo obbligatorio a inizio partita

Prima di qualunque consiglio, l'advisor deve calcolare e mostrare:

1. **Pip per risorsa** (tabella a 5 voci) e scostamento dalla quota attesa → quali risorse sono scarse *in questa partita*.
2. **Top 10 incroci** per pip grezzo e per S(v).
3. **Cluster geografici**: quali zone del tabellone concentrano i pip. Di solito il tabellone ha 2–3 "zone calde"; la competizione si concentra lì.
4. **Mappa dei porti** con la risorsa adiacente: quali porti sono "naturalmente" serviti da tessere vicine.
5. **Numero di incroci con S(v) ≥ soglia** — serve per la teoria del draft (§C.1).

---

# PARTE C — STRATEGIA CONTESTUALE

## C.1 Teoria del draft: valore relativo, non assoluto

Il valore reale di un pick non è `S(v)`, ma:

```
VOR(v) = S(v) − E[miglior incrocio disponibile al mio prossimo pick]
```

(VOR = Value Over Replacement)

**Come stimarlo:** se ci sono `k` pick prima del tuo prossimo turno, e ogni pick avversario brucia mediamente **2.5 incroci di qualità** (quello preso + quelli invalidati dalla distance rule + quelli devalorizzati dalla condivisione tessere), allora spariranno circa `2.5 × k` incroci dalla cima della lista.

```
4 giocatori, P1: k=6 → spariranno ~15 incroci → al pick #8 prendo circa il 16° miglior incrocio
4 giocatori, P4: k=0 → il mio secondo pick è il migliore rimasto in assoluto
```

**Regola operativa:**
> Se il numero di incroci con `S(v) ≥ X` è **maggiore** del numero di incroci che spariranno prima del tuo prossimo pick, puoi permetterti un pick "egoista" (massimo pip) e sistemare la complementarità dopo.
> Se è **minore o uguale**, devi già ora prendere un incrocio che funzioni come metà di una coppia realistica.

## C.2 Strategia per posizione

### 4 giocatori

**Posizione 1 (pick #1 e #8)**
- Hai il miglior incrocio del tabellone: **prendilo, senza compromessi**. Massimizza `S(v)` puro, con preferenza per 3 risorse distinte.
- Il pick #8 sarà uno scarto. Devi quindi scegliere una prima colonia **il più possibile autosufficiente** (3 risorse diverse, alta produzione) e non dipendente da un secondo pick specifico.
- Preferisci una prima colonia in una zona con **spazio di espansione**, perché quando toccherà a te di nuovo il tabellone sarà congestionato.
- Al pick #8: cerca (a) le risorse mancanti, (b) un porto 2:1 sulla tua risorsa ridondante, (c) un incrocio che rompa l'espansione di un avversario forte.
- **Compensazione:** giochi per primo → un turno di vantaggio in tempo di costruzione per tutta la partita. Con un'apertura da 20+ pip questo si traduce spesso nella prima colonia extra.

**Posizione 4 (pick #4 e #5, consecutivi)**
- **Pianifica i due pick come un unico pacchetto.** È il tuo vantaggio strutturale: hai informazione completa e nessun rischio di interferenza.
- Obiettivo: coppia con **copertura 5/5** o 4/5 + porto 2:1, e due motori attivi (espansione + città).
- Puoi permetterti un incrocio "specializzato" (es. porto 2:1 pecora) perché lo compensi immediatamente con l'altro.
- Prendi anche in considerazione un **pick di blocco** al #5 se un avversario ha lasciato scoperto un incrocio che gli serve per il piano evidente — ma solo se la perdita di `S(v)` è < 1.5.
- **Svantaggio:** giochi per ultimo. Serve produzione più alta per compensare il tempo perso.

**Posizioni 2 e 3**
- Devi **anticipare**: al tuo primo pick, chiediti quali risorse saranno già state prese e quali resteranno.
- P3 (pick #3 e #6, k=2): quasi come P4, puoi pianificare la coppia con buona confidenza.
- P2 (pick #2 e #7, k=4): situazione più scomoda. Prendi il meglio disponibile ma con **almeno 2 risorse fra grano/minerale/mattone**, perché al pick #7 quelle saranno finite.
- Regola per P2/P3: se al primo pick vedi che una risorsa **scarsa** (quella con quota_r più bassa) è ancora libera su un buon numero, prendila **adesso**. Le risorse scarse non tornano.

### 3 giocatori — differenze sostanziali

- **Meno tiri per giro** (3 invece di 4) → produzione assoluta più lenta, partita più lunga in numero di turni.
- **Molto più spazio**: il tabellone resta aperto. L'espansione e la **strada più lunga** valgono di più.
  → alza `W_legno` e `W_mattone` di circa +0.1 e aumenta il peso del bonus espansione (×1.4).
- **Il blocco vale meno**: c'è quasi sempre un'alternativa. Non sprecare pip per bloccare.
- **Puoi prenderti un porto prima**, anche al primo pick se la combo è forte, perché la competizione è bassa.
- **Il ladro ti colpisce meno spesso** (1 avversario in meno che tira 7) → puoi permetterti un incrocio più concentrato su 6/8.
- Il mercato degli scambi è più rigido: con 2 soli partner, una risorsa mancante è molto più pericolosa. **La copertura 5/5 sale di priorità** (bonus da +3.0 a +4.0).

## C.3 Lettura degli avversari

L'advisor deve mantenere, per ogni avversario già piazzato, un profilo:

```
avversario_i = {
    risorse_coperte: {legno: pip, mattone: pip, grano: pip, pecora: pip, minerale: pip},
    risorse_mancanti: [...],
    pip_totali: N,
    numeri_coperti: [...],
    porti: [...],
    direzione_strade: [...],
    archetipo_stimato: "espansione" | "città" | "carte" | "bilanciato" | "porto"
}
```

### Cosa farne

**1. Mercato degli scambi**
- Una risorsa **che nessun avversario produce** e che tu produci = potere di monopolio per tutta la partita. Vale un premio di **+1.5** sul punteggio.
- Una risorsa che **tutti** producono = valore di scambio quasi nullo. Se la tua produzione è concentrata lì, sei in guai: penalità **−1.0**.
- Regola: il valore di scambio di una risorsa dipende dalla **scarsità relativa fra i giocatori**, non dal numero di tessere.

**2. Partner e rivali**
- Il tuo **partner naturale di scambio** è chi ha risorse complementari alle tue *e* non è in corsa diretta con te.
- Il tuo **rivale diretto** è chi condivide la tua zona di espansione. Piazzarsi lontano da giocatori forti è spesso meglio che condividere una zona calda.
- A 4 giocatori, piazzare le due colonie in **due zone diverse** riduce il rischio di essere strozzato, ma rallenta l'espansione (le strade non si collegano). Trade-off da segnalare esplicitamente.

**3. Copertura numerica del tavolo**
- Se tutti sono carichi su 6 e 8, il ladro vivrà lì e quei numeri renderanno meno del previsto.
- Un incrocio su numeri "trascurati" dal tavolo (es. 5, 9, 10) è più tranquillo: **+0.5** se nessun avversario ha quei numeri su tessere condivise.

**4. Condivisione tessere**
- Se condividi una tessera con un avversario, quella tessera diventa un bersaglio del ladro **due volte più attraente** per gli altri, ma anche un deterrente reciproco. Effetto netto leggermente negativo: **−0.3 per tessera condivisa con il leader percepito**.

### Blocco: quando conviene

Blocca **solo se** vale tutte e tre:
1. È il tuo **ultimo** pick (o sei a 3 giocatori con k=0).
2. Il costo per te è **< 1.5 punti** di `S(v)` rispetto alla tua alternativa migliore.
3. L'avversario bloccato ha un piano **evidente e forte** che dipende da quell'incrocio (es. l'unico modo per attivare il suo porto 2:1, o il suo unico accesso al minerale).

Altrimenti: **non bloccare mai**. Il blocco che ti costa produzione fa vincere il terzo giocatore.

## C.4 Archetipi strategici

L'advisor deve identificare quale archetipo la coppia proposta abilita, e dirlo esplicitamente.

### 1. Grano-Minerale-Pecora (città + carte sviluppo)
- **Profilo:** grano ≥ 6 pip, minerale ≥ 6 pip, pecora ≥ 3 pip. Porto 2:1 pecora o minerale è un moltiplicatore.
- **Piano:** poche colonie, città rapide, carte sviluppo per Esercito più grande (+2 PV) e carte punto.
- **Punti:** 2 colonie iniziali (2) + 3-4 città (6-8) + esercito (2) + carte punto.
- **Forza:** scala meglio di tutto nel late game. Il cavaliere sposta il ladro e difende.
- **Debolezza:** lentissimo nei primi 5-6 turni, poco spazio occupato, vulnerabile se il tabellone si chiude.
- **Quando:** posizione tardiva nel draft, tabellone con minerale su numeri alti, 4 giocatori.

### 2. Legno-Mattone (espansione + strada più lunga)
- **Profilo:** legno ≥ 5 pip, mattone ≥ 5 pip, grano ≥ 4 pip.
- **Piano:** strade e colonie a raffica nei primi turni, occupa lo spazio, prendi la strada più lunga (+2 PV).
- **Punti:** 5 colonie (5) + 1-2 città (2-4) + strada lunga (2).
- **Forza:** velocissimo, prende gli incroci migliori residui, nega spazio agli altri.
- **Debolezza:** si spegne quando finisce lo spazio; senza minerale non converte in città; le colonie rendono metà delle città.
- **Quando:** 3 giocatori, tabellone aperto, posizione precoce nel draft.

### 3. Bilanciato
- **Profilo:** 5/5 risorse, nessuna sotto 3 pip, pip totali ≥ 19.
- **Piano:** espandi a 3-4 colonie, poi converti in città.
- **Forza:** robusto, indipendente dagli scambi, resiste al ladro.
- **Debolezza:** non eccelle in nulla; perde contro un archetipo puro ben eseguito su un tabellone favorevole.
- **Default consigliato** se non c'è un motivo forte per specializzarsi.

### 4. Porto/monopolio
- **Profilo:** una risorsa con ≥ 8 pip + porto 2:1 corrispondente.
- **Piano:** converti il surplus in qualunque cosa serva, indipendenza totale dagli scambi.
- **Forza:** immune al blocco commerciale, ottimo contro tavoli ostili.
- **Debolezza:** il tasso 2:1 è comunque inefficiente; se il ladro presidia la tua tessera chiave sei fermo.
- **Requisito:** serve un secondo pick con almeno 3 risorse diverse per non collassare.

---

# PARTE D — IMPLEMENTAZIONE

## D.1 Schema dati del tabellone

Coordinate esagonali **assiali** `(q, r)` per i 19 esagoni. Vertici identificati come tripla ordinata di esagoni adiacenti (per i vertici interni) o come coppia + marcatore costa.

```json
{
  "players": 4,
  "my_position": 2,
  "hexes": [
    {"id": "h01", "q": 0, "r": -2, "resource": "ore",   "number": 10},
    {"id": "h02", "q": 1, "r": -2, "resource": "sheep", "number": 2},
    {"id": "h10", "q": 0, "r": 0,  "resource": "desert","number": null}
  ],
  "vertices": [
    {"id": "v01", "hexes": ["h01","h02","h05"], "port": null},
    {"id": "v02", "hexes": ["h01","h02"], "port": {"type": "2:1", "resource": "ore"}}
  ],
  "edges": [
    {"id": "e01", "vertices": ["v01","v02"]}
  ],
  "placements": [
    {"player": 1, "vertex": "v14", "road_edge": "e22", "order": 1}
  ]
}
```

**Input semplificato per l'uso reale** (inserire un tabellone completo a mano è troppo lento): permettere all'utente di descrivere solo gli incroci candidati che sta valutando, es. `"6-grano, 9-minerale, 5-legno, porto 3:1"`, più l'elenco dei piazzamenti avversari nello stesso formato. L'advisor lavora in modalità degradata ma utile.

## D.2 Pseudocodice del motore

```python
def consiglia_apertura(board, my_position, n_players, placements_so_far):
    # 1. Pre-calcolo globale
    scarcity = calcola_scarsita_risorse(board)      # §B.2
    W = pesi_risorse(scarcity, n_players)           # §B.2 + §C.2 (3p vs 4p)
    opponents = profila_avversari(placements_so_far) # §C.3

    # 2. Valuta ogni incrocio legale
    legal = [v for v in board.vertices if is_legal(v, placements_so_far)]
    scored = []
    for v in legal:
        s = pip_pesato(v, W)
        s += bonus_diversita(v) + bonus_espansione(v, board, placements_so_far)
        s += valore_porto(v, portafoglio_ipotetico=None)
        s += bonus_mercato(v, opponents)            # §C.3
        s -= malus_ladro(v) + malus_condivisione(v, opponents)
        scored.append((v, s))

    # 3. Ramo: primo o secondo pick?
    if e_primo_pick(my_position, placements_so_far):
        k = pick_di_attesa(my_position, n_players)
        # simula quali incroci sopravvivranno
        survivors = simula_erosione(scored, k, erosion_rate=2.5)
        # per ogni candidato top-N, valuta la MIGLIORE coppia attesa
        best = []
        for v, s in top_n(scored, 8):
            partner_atteso = max(compatibili(v, survivors),
                                 key=lambda u: S_coppia(v, u, W))
            best.append((v, s, S_coppia(v, partner_atteso, W)))
        return ordina_per(best, chiave="S_coppia_attesa")
    else:
        # secondo pick: coppia esatta, informazione completa
        A = mia_colonia_esistente
        return ordina([(B, S_coppia(A, B, W)) for B, _ in scored])
```

## D.3 Formato dell'output atteso

Per ogni raccomandazione l'advisor deve restituire:

```
🥇 RACCOMANDAZIONE #1 — Incrocio [8-grano / 5-minerale / 9-legno]
   Pip: 14 (pesato 15.8)  |  Risorse: grano, minerale, legno

   PERCHÉ:
   • 14 pip è il 2° valore del tabellone, con 3 numeri distinti in fascia media
   • Copre grano E minerale, le due risorse che P1 e P3 hanno già preso —
     saranno impossibili da ottenere via scambio
   • Il minerale in questa partita è su 5-8-9 (17 pip su 58): non è scarso,
     ma tu ne prendi la fetta migliore
   • 2 incroci di espansione a 1 strada con pip ≥8 (verso il porto 2:1 grano)

   RISCHI:
   • Zero mattone e zero pecora: al 2° pick DEVI coprirli entrambi
   • L'8-grano è condiviso con P3 → tessera bersaglio del ladro

   STRADA CONSIGLIATA: verso [v27], che prenota l'incrocio 6-mattone/4-pecora
   — copre esattamente i tuoi due buchi ed è a 2 strade dal porto 2:1 grano.

   PIANO DI COPPIA: se al pick #7 [v27] è ancora libero → apertura da 22 pip
   con copertura 5/5. Se lo perdi, fallback su [v33] (6-mattone/3-pecora, −2 pip).

   ARCHETIPO ABILITATO: Città + carte sviluppo, con espansione moderata.
```

Sempre includere **almeno 3 opzioni** e almeno **1 fallback** per opzione, perché in un draft il piano A salta spesso.

## D.4 Parametri da calibrare

Tutti i pesi vanno esposti in un file di configurazione. Valori iniziali da testare:

```yaml
resource_weights:      {wheat: 1.20, ore: 1.10, brick: 1.10, wood: 1.00, sheep: 0.80}
scarcity_exponent:     0.5
diversity_3:           2.0
diversity_2:           0.3
monoculture_penalty:   -2.5
expansion_bonus_1road: 0.9
expansion_bonus_2road: 0.4
port_2to1_high:        3.2
port_3to1_base:        0.4
synergy_full_coverage: 3.0     # 4.0 se n_players == 3
erosion_rate:          2.5     # incroci bruciati per pick avversario
robber_penalty:        0.6
monopoly_bonus:        1.5
```

**Come calibrare:** non scrivere un simulatore. Usa Catanatron — vedi §E.4 per il metodo concreto (Optuna o SPSA su partite reali simulate).

## D.5 Anti-pattern da codificare come warning

L'advisor deve emettere un avviso esplicito in questi casi:

1. **Porto senza produzione** — porto 2:1 su risorsa con < 3 pip.
2. **Zero grano** o grano < 4 pip nella coppia.
3. **Legno o mattone a 0** — non potrai costruire strade, resti bloccato a 2 colonie.
4. **Tutto su 6 e 8** — grande su carta, ma il ladro vivrà su di te tutta la partita.
5. **Inseguire i pip ignorando la 5ª risorsa** — 24 pip su 3 risorse perde contro 20 pip su 5.
6. **Bloccare al primo pick** — non si blocca mai quando hai ancora un pick a venire.
7. **Due colonie che condividono le stesse tessere** — raddoppi la varianza invece di diversificarla.
8. **Strada iniziale sprecata** — verso il mare, verso il deserto senza sbocco, o verso un incrocio già invalidato dalla distance rule.
9. **Pecora sovrappesata** — è la risorsa con il peggior tasso di scambio; oltre 6 pip senza porto 2:1 pecora è surplus morto.
10. **Ignorare l'ordine di turno** — a 4 giocatori, P1 con 19 pip è spesso meglio di P4 con 21 pip: il tempo vale.

---

## Appendice — Riepilogo delle priorità in ordine

Quando i segnali sono in conflitto, questo è l'ordine di precedenza:

1. **Vincoli hard di coppia** (grano ≥4, copertura ≥4/5, legno&mattone >0)
2. **Pip pesati totali** della coppia
3. **Diversità numerica** (non dipendere da 2 numeri)
4. **Risorse scarse su questo tabellone e su questo tavolo** (potere di mercato)
5. **Spazio di espansione**
6. **Porti**
7. **Blocco avversari**

> Il consiglio finale non è mai "questo incrocio", ma sempre **"questo incrocio, con questo piano di coppia, questa strada, e questo fallback"**.

---

# PARTE E — EVIDENZE DA CATANATRON (v2)

Questa parte deriva dall'**ispezione diretta del codice sorgente di Catanatron** (`bcollazo/catanatron`, GPL-3.0-or-later), il simulatore/bot open source più forte per Catan. I pesi qui sotto non sono stime: sono valori **tarati automaticamente** con Optuna e SPSA su decine di migliaia di partite simulate.

> **Caveat importante da tenere sempre presente:** la funzione di valutazione di Catanatron valuta lo **stato di gioco completo**, non specificamente l'apertura. Il bot piazza le colonie iniziali usando la stessa funzione. Quindi i suoi pesi sono **evidenza forte ma indiretta** per la fase di setup. Vanno usati per correggere le mie stime a priori, non per sostituire il ragionamento sull'apertura (draft order, porti, avversari — cose che Catanatron **non** modella).

## E.1 Unità di misura corretta: carte attese per tiro

Catanatron non usa i pip. Usa direttamente la **probabilità**:

```python
proba_point = 2.778 / 100      # = 1/36, il valore di 1 pip
```

La produzione di un incrocio è la somma delle probabilità delle tessere adiacenti che producono una data risorsa. **Una città conta ×2.** La produzione "effettiva" **sottrae la tessera occupata dal ladro**.

**Conversione per il tuo advisor:**

```
carte_attese_per_tiro(v) = pip_totali(v) / 36
carte_attese_per_giro(v) = carte_attese_per_tiro(v) × n_players
```

| Pip | Carte/tiro | Carte/giro (4p) |
|---|---|---|
| 8 | 0.222 | 0.89 |
| 10 | 0.278 | 1.11 |
| 12 | 0.333 | 1.33 |
| 20 (coppia) | 0.556 | 2.22 |
| 22 (coppia) | 0.611 | 2.44 |

**Usa questa unità nell'output.** "La tua coppia produce 2.4 carte a giro" è molto più azionabile di "22 pip". E rende immediato il confronto: la differenza fra un'apertura da 22 e una da 18 pip è ~0.44 carte a giro, cioè **circa una colonia in più ogni 9 giri**.

## E.2 La diversità delle risorse vale molto più del previsto

Il valore più sorprendente trovato nel codice:

```python
TRANSLATE_VARIETY = 4  # i.e. each new resource is like 4 production points
```

**Ogni risorsa distinta prodotta vale quanto 4 pip di produzione aggiuntiva.**

Nella v1 di questo documento avevo stimato il salto da 2 a 3 risorse a circa +1.7 pip-equivalenti. Il valore reale è **+4**. Ho corretto §B.3 e §B.4 di conseguenza.

Due implicazioni operative:

1. **Una coppia 5/5 da 19 pip batte una coppia 3/5 da 23 pip.** In pip-equivalenti: 19 + 20 = 39 contro 23 + 12 = 35.
2. **Il bonus va applicato al portafoglio, non al singolo incrocio.** Nel codice la varietà è calcolata sulla produzione totale del giocatore, sommando tutti gli edifici. Un incrocio monorisorsa non è un errore in sé — lo diventa solo se anche l'altra colonia non compensa. Questo giustifica pick "specializzati" (es. porto 2:1 + tessera forte) purché la coppia chiuda il cerchio.

Nota tecnica: la varietà **non** viene conteggiata quando si valuta la produzione avversaria (`include_variety=False`). Cioè, quando profili un avversario, guarda i suoi pip grezzi; quando valuti te stesso, guarda pip + varietà.

## E.3 La gerarchia dei pesi — la lezione architetturale principale

Questi sono i pesi tarati (`CONTENDER_WEIGHTS`), ordinati per magnitudine:

| Termine | Peso | Ordine |
|---|---|---|
| `public_vps` | 3.0e14 | 10¹⁴ |
| `production` | 1.0e8 | 10⁸ |
| `enemy_production` | −1.0e8 | 10⁸ |
| `reachable_production_1` | 1.0e4 | 10⁴ |
| `buildable_nodes` | 1.0e3 | 10³ |
| `hand_synergy` | 1.0e2 | 10² |
| `army_size` | 12.9 | 10¹ |
| `longest_road` | 12.1 | 10¹ |
| `hand_devs` | 10.7 | 10¹ |
| `num_tiles` | 2.9 | 10⁰ |
| `hand_resources` | 2.4 | 10⁰ |
| `discard_penalty` | −3.0 | 10⁰ |
| `reachable_production_0` | 2.0 | 10⁰ |

**Sono separati da ordini di grandezza: la funzione è di fatto quasi lessicografica.** Non è una media pesata, è una cascata di priorità.

Cosa significa per l'advisor di apertura:

1. **La produzione domina tutto tranne i punti vittoria.** Nella fase di setup i PV sono fissi (2 colonie = 2 PV per tutti), quindi in apertura **la produzione è il criterio dominante, punto**. Tutto il resto è tie-breaker.
2. **`reachable_production_1` (10⁴) è quattro ordini sotto la produzione ma tre sopra la strada più lunga.** Conferma che il potenziale di espansione è un criterio di secondo livello reale — ma conferma anche che **non si sacrificano mai pip per prendere spazio.** Ho tarato di conseguenza il bonus espansione in §B.3 (0.9 max su una scala dove i pip valgono 1.0 ciascuno: giusto).
3. **`reachable_production_0` è a 2.0, praticamente zero.** La produzione già raggiungibile senza costruire strade non aggiunge valore — è già contata nella produzione. Non contare due volte.
4. **Conta la PRODUZIONE raggiungibile, non il numero di incroci raggiungibili.** Un incrocio libero a 1 strada che produce 4 pip vale il doppio di uno che ne produce 2. La mia §B.3 li trattava come binari (pip ≥ 8 sì/no): sostituisci con un valore continuo.
5. **`longest_road` e `army_size` sono a 10¹, cioè irrilevanti come euristiche dirette.** Contano solo attraverso i PV che generano. **Non pianificare l'apertura attorno alla strada più lunga.**

### La regola condizionale più interessante del codice

```python
longest_road_factor = params["longest_road"] if num_buildable_nodes == 0 else 0.1
```

**La strada più lunga vale il suo peso pieno solo quando non hai più nodi costruibili.** Altrimenti vale 1/120 di quello.

Tradotto in strategia: *insegui la strada più lunga solo quando l'espansione è fisicamente bloccata.* Questo rivede al ribasso l'archetipo "Legno-Mattone / strada lunga" di §C.4 — quella strategia non è un piano di apertura, è un **piano di ripiego** che si attiva quando il tabellone si chiude. Con 3 giocatori (tabellone che resta aperto a lungo) è ancora meno prioritaria di quanto avevo scritto.

### Sulla produzione avversaria

`enemy_production` ha peso **esattamente opposto e uguale** a `production` (−1e8 contro +1e8): togliere un pip a un avversario vale quanto guadagnarne uno.

**Ma attenzione a due limiti prima di usarlo per giustificare il blocco:**
- Nel codice viene valutato **un solo avversario** (`P1`, il giocatore successivo), non tutti. È una semplificazione forte.
- Il termine misura la produzione avversaria in **generale**, non "quanto gli tolgo bloccandolo". In apertura, occupare un incrocio non riduce la produzione di nessuno: gli toglie solo un'opzione.

Quindi **la mia raccomandazione originale di §C.3 resta valida**: blocca raramente e solo all'ultimo pick. Il peso simmetrico conferma però che **profilare gli avversari è un termine di primo livello**, non un dettaglio.

## E.4 Calibrazione: come tarare i tuoi pesi davvero

Catanatron include due ottimizzatori già pronti che lavorano su `play_batch`:

- **`optunation.py`** — Optuna, ottimizzazione bayesiana. Ogni parametro campionato in `[0, 100]`, obiettivo = win rate contro un avversario di riferimento.
- **`spsa.py`** — SPSA (l'algoritmo usato per tarare i motori scacchistici), 1000 iterazioni. Commento dell'autore nel sorgente: funziona.

**Metodo consigliato per il tuo progetto:**

1. Implementa un `Player` custom in Catanatron che, **solo nella fase di setup**, usa la funzione di valutazione della Parte B; per il resto della partita usa `ValueFunctionPlayer` standard.
2. Fai giocare N migliaia di partite contro `ValueFunctionPlayer` puro.
3. Se il tuo win rate supera il 25% (4 giocatori) con significatività statistica, la tua euristica di apertura è **migliore di quella del miglior bot open source**.
4. Usa SPSA o Optuna per tarare i pesi di §D.4 sullo stesso obiettivo.

```bash
pip install catanatron
git clone https://github.com/bcollazo/catanatron.git
catanatron-play --players=R,R,R,W --num=1000
```

Struttura di un player custom:

```python
from catanatron import Player
class OpeningAdvisorPlayer(Player):
    def decide(self, game, playable_actions):
        # game.state è read-only e contiene tutto
        return scelta
```

**Questo è il vantaggio più grosso che puoi ottenere:** ti dà un numero oggettivo — win rate — invece di un'opinione sulla bontà dell'apertura.

## E.5 Non costruire un MCTS

L'autore di Catanatron documenta di aver provato Monte Carlo Tree Search: anche con 10.000 simulazioni per turno veniva battuto abbastanza facilmente da un giocatore umano, ed era **peggiore** del ValueFunctionPlayer a pesi fissi. In Python, 100 simulazioni costavano ~3 secondi per turno.

**Conclusione: l'approccio corretto per il tuo progetto è una funzione di valutazione pesata e interpretabile.** Ha tre vantaggi decisivi qui: è veloce, è tarabile, e soprattutto **è spiegabile** — può dirti *perché* un incrocio è buono, cosa che un MCTS non fa. Dato che l'obiettivo è consigliare te, non giocare al posto tuo, la spiegabilità è il requisito numero uno.

## E.6 Due metriche aggiuntive da adottare

### Antifragilità al ladro (`num_tiles`)

Catanatron conta le **tessere distinte** toccate dagli edifici di un giocatore (peso basso, ~2.9). È un proxy di resistenza al ladro: se le tue 2 colonie toccano 6 tessere distinte, il ladro ti toglie al massimo 1/6 della produzione; se ne toccano 4 (perché condividono tessere), te ne toglie 1/4.

```
+ 0.25 per tessera distinta toccata dalla coppia   (range: 2–6)
```

Rafforza l'anti-pattern #7 di §D.5: due colonie che condividono tessere sono doppiamente penalizzate — meno diversificazione numerica **e** più esposte al ladro.

### Clustering spaziale delle risorse

Idea presa dall'algoritmo di bilanciamento di `Ivanov1ch/Catan`: si tracciano tre **linee divisorie** che attraversano il centro del tabellone senza intersecare posizioni valide di colonia, e si confronta la distribuzione di ogni risorsa sui due lati.

Uso per l'advisor: calcolare, per ogni risorsa, un **indice di concentrazione spaziale**.

```
Se una risorsa scarsa (mattone o minerale) è fortemente clusterizzata:
  → chi occupa quel cluster ha il monopolio per tutta la partita
  → alza il valore degli incroci in quel cluster di +1.5
  → segnala esplicitamente: "il minerale è tutto in questa zona, se non
     lo prendi ora non lo prendi più"

Se è distribuita uniformemente:
  → nessun premio, ci sarà sempre un'alternativa
```

Questo è il ponte fra "scarsità numerica" (§B.2, quanti pip) e "scarsità pratica" (quanti giocatori possono realisticamente accedervi).

## E.7 Cosa Catanatron NON fa — il tuo spazio di differenziazione

Verificato per ispezione: la sua funzione di valutazione **non contiene alcun termine** per:

| Aspetto | Presente in Catanatron? | Presente in questa KB |
|---|---|---|
| Ordine di piazzamento / draft (VOR) | ❌ | §C.1–C.2 |
| Porti in relazione al portafoglio | ❌ | §B.5 |
| Scarsità relativa fra i giocatori (mercato scambi) | ❌ | §C.3 |
| Scarsità dinamica del tabellone | ❌ | §B.2 |
| Pianificazione della coppia come unità | ❌ | §B.4 |
| Spiegazione del consiglio | ❌ | §D.3 |

Anche gli altri strumenti online esaminati (CatanCalculator, Catan Board Analyzer, Catanalyzer) sono **contatori di pip**: colorano gli incroci per probabilità e si fermano lì.

**Il differenziale del tuo progetto è tutto qui.** La matematica della produzione è risolta e la puoi prendere in prestito. Il valore che aggiungi è il **contesto**: chi sei nel draft, chi ha già piazzato cosa, e quale piano di coppia stai eseguendo.

## E.8 Input del tabellone da foto

Esistono implementazioni OpenCV di riconoscimento del tabellone da immagine (es. `stuartbourne/catan_board_analyzer`). Data l'esistenza di prior art, questa è la via consigliata per l'input.

Ma per il tuo caso c'è una scorciatoia migliore: **Claude legge le immagini nativamente.** Non serve una pipeline OpenCV — basta un prompt strutturato che, data una foto del tabellone, produca il JSON di §D.1. Va gestita l'ambiguità (numeri sfocati, tessere in prospettiva) con una richiesta di conferma sugli esagoni a bassa confidenza.

Pipeline suggerita:

```
foto → estrazione JSON (visione) → conferma utente sugli esagoni incerti
     → pre-calcolo §B.6 → advisor
```

---

## Changelog v1 → v2

| Cosa | Prima | Dopo | Fonte |
|---|---|---|---|
| Unità di output | pip | carte attese per tiro/giro | `proba_point` |
| Diversità risorse (coppia) | +3.0 per 5/5 | **+8.0 per 5/5** | `TRANSLATE_VARIETY = 4` |
| Diversità (singolo incrocio) | +2.0 | +1.5 per risorsa, peso spostato sulla coppia | varietà calcolata a livello giocatore |
| Bonus espansione | binario (pip ≥ 8) | continuo, proporzionale alla produzione raggiungibile | `reachable_production_1` |
| Strada più lunga | archetipo di apertura | **piano di ripiego**, attivo solo a espansione bloccata | `longest_road_factor` |
| Tessere distinte | non modellato | +0.25 ciascuna (antifragilità ladro) | `num_tiles` |
| Clustering risorse | non modellato | indice di concentrazione spaziale | `Ivanov1ch/Catan` |
| Calibrazione | simulatore da scrivere | Optuna/SPSA su Catanatron | `optunation.py`, `spsa.py` |
| MCTS | opzione aperta | **scartato** | benchmark documentati |
