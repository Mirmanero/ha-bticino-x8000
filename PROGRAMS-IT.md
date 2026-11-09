# Gestione programmi BTicino — beta 1.3.0-beta.4

Questa versione aggiunge un editor grafico e una selezione del programma attivo. I programmi sono salvati nel termostato: HA serve per modificarli o selezionarli, non per inviare una temperatura a ogni fascia.

## Installazione tramite Studio Code Server

1. Salva una copia dell'attuale cartella `/config/custom_components/bticino_thermostat` fuori da `custom_components`.
2. Estrai il pacchetto e sostituisci il contenuto completo della cartella omonima, includendo la nuova cartella `frontend`.
3. Riavvia completamente Home Assistant. Mantieni la configurazione dell'integrazione esistente; non devi reinserire PIN o account. Se era stata disabilitata per le prove via VPN, riattiva l'integrazione locale.
4. Apri **Impostazioni → Plance → menu in alto a destra → Risorse** e aggiungi:

   ```text
   /bticino_thermostat_static/bticino-programs-card.js?v=1.3.0-beta.4
   ```

   Scegli il tipo **Modulo JavaScript**. Se la gestione delle risorse è configurata in YAML, aggiungi lo stesso URL come risorsa `module` nella configurazione esistente.

5. Ricarica la pagina del browser. In una plancia, aggiungi la scheda **BTicino Programs** e scegli il termostato dall'editor grafico.

In alternativa, usa una scheda manuale:

```yaml
type: custom:bticino-programs-card
entity: climate.il_tuo_termostato
```

Sostituisci l'entità con quella del dispositivo. Non serve copiare JavaScript in `www`: viene servito dall'integrazione.

## Cosa trovi

- Due viste: **Programmi** per consultare/modificare la settimana e **Oggi** per la giornata del programma in esecuzione.
- In alto: selezione del programma da attivare.
- A lato, o in alto sul telefono: elenco dei programmi salvati.
- Una vista delle fasce di tutta la settimana.
- Per ogni giorno: orari, livelli e copia delle fasce ad altri giorni.
- Creazione, duplicazione, importazione/esportazione JSON e salvataggio sul termostato.
- Eliminazione di programmi non attivi, con conferma.

Per cambiare le fasce, scegli un programma e un giorno, poi premi **Modifica fasce**. Ogni riga mostra inizio, fine e livello: la fine è ricavata dall'inizio della fascia successiva. **Fine modifica** torna alla consultazione senza salvare; premi **Salva sul termostato** per confermare le modifiche. La copia dei giorni è disponibile durante la modifica. Duplicazione, importazione, esportazione ed eliminazione sono raccolte in **Altre opzioni**.

## Scheda Oggi per la plancia

La stessa risorsa JavaScript registra anche **BTicino Today**, una scheda di sola consultazione. Aggiungila dall'elenco schede, oppure usa:

```yaml
type: custom:bticino-today-card
entity: climate.il_tuo_termostato
```

La scheda autonoma mostra **solo la barra del tempo 00:00-24:00**, con fasce colorate proporzionali alla durata, temperature e cursore dell'ora attuale. Non contiene titolo, riepiloghi o elenco delle fasce: è pensata per essere inserita accanto alle altre schede della dashboard. Gli orari precisi sono disponibili nella descrizione di ogni segmento, passando il mouse o tramite lettore di schermo.

La vista completa resta nella scheda Oggi dell'editor. Per abilitarla anche nella scheda autonoma, aggiungi facoltativamente `show_details: true` alla configurazione YAML. La fascia prevista usa il fuso orario configurato in Home Assistant e l'orologio del browser: non è una conferma del relè o dell'orologio interno del dispositivo. La schermata aggiorna l'orario ogni 30 secondi, senza inviare comandi al termostato; a mezzanotte cambia giorno automaticamente.

Durante Manuale, Boost, Protezione o Off, il programma non viene mostrato come in esecuzione. Se il dispositivo è scollegato, le eventuali fasce memorizzate restano consultabili ma non sono evidenziate come attive. Un piccolo indicatore segnala lo stato nella barra. Usa **Aggiorna** nell'editor o il pulsante nativo **Aggiorna programmi** per rileggere modifiche fatte nell'app. La vista Oggi usa sempre il programma salvato e attivo, anche se stai modificando una bozza diversa nell'editor.

## Fasce e livelli

Il primo orario è sempre `00:00`; ogni livello resta valido fino all'orario successivo. Per una fase 10:00–11:00, inserisci il livello desiderato alle 10:00 e quello successivo alle 11:00. Sono consentite fino a otto fasce per giorno in questa beta.

I livelli Giorno, Notte, Fuori casa e Protezione sono quelli configurati sul termostato. La scheda mostra anche i gradi quando disponibili, ma non modifica le temperature globali. Se ne viene segnalata la verifica incompleta, confrontale con l'app.

Un nuovo programma viene salvato senza attivarlo. Puoi attivarlo dal menu in alto o dal pulsante dedicato dopo il salvataggio. Se modifichi il programma già attivo, le nuove fasce aggiornano quello in uso: la scheda lo segnala.

Sono disponibili anche due entità native nella pagina del dispositivo:

- **Programma attivo**, utilizzabile con la normale azione `select.select_option`.
- **Aggiorna programmi**, per rileggere quelli modificati nell'app.

Gli identificativi delle entità dipendono dai nomi e dal registro del tuo HA: cercali nella pagina del termostato. Durante una forzatura manuale/Boost/Protezione, il selettore non mostra un programma attivo; selezionandone uno si torna in Automatico.

## Prima prova consigliata

La lettura e la creazione di un nuovo file sono state verificate su X8000 reale. L'interfaccia completa è stata provata offline nel browser con HA simulato: resta da verificare sulla tua installazione.

1. Premi Aggiorna e confronta elenco e fasce con Thermostat.
2. Duplica un programma in uno spazio libero; cambia nome o orario e salva senza attivarlo.
3. Riapri il programma e confrontalo nell'app. Il backend rilegge il file e ne verifica il checksum prima di confermare il salvataggio.
4. Prova la selezione soltanto in un momento supervisionato, poi ripristina il programma desiderato.
5. L'eliminazione va provata solo su un programma di test non attivo. Il programma predefinito zero e quello attivo sono protetti.

Per modificare dal nuovo editor serve un account amministratore. Le entità native seguono le normali autorizzazioni HA.

## Salvataggi, conflitti e ripristino

Prima di modificare/eliminare un programma esistente, HA ne conserva una copia. Se la copia non può essere salvata, la scrittura sul termostato viene fermata. Le ultime venti copie per dispositivo sono mantenute nella memoria persistente di HA; questa beta non ha ancora una schermata per ripristinarle automaticamente.

Se il programma è cambiato nell'app dopo l'apertura dell'editor, il salvataggio viene bloccato. Puoi esportare la bozza prima di ricaricare. Per un esito incerto o una perdita di connessione, premi Aggiorna e controlla il programma: non ripetere il salvataggio alla cieca.

Per tornare alla vecchia integrazione, ripristina la cartella salvata e riavvia HA; rimuovi anche la nuova risorsa dalla plancia. I programmi del dispositivo restano memorizzati.

La VPN serve solo per eventuali prove dirette da questo PC. L'editor usa la connessione locale già aperta da HA. Se un client VPN deve collegarsi separatamente al termostato, può essere necessario disabilitare temporaneamente l'integrazione locale per liberare la connessione.

## Per il futuro fork/PR

I dettagli tecnici e i limiti sono in `PROGRAMS.md`; i test sono riproducibili con `requirements-dev.txt`, `tests/run_offline.py` e `npm run test:frontend`. La scheda non richiede Node.js su HA e non carica librerie esterne.

La creazione del programma test è stata verificata sul dispositivo. L'utente ha inoltre confermato il funzionamento della beta nella propria installazione HA; i singoli casi della checklist, comprese modifica, eliminazione e autorizzazioni, restano da verificare prima di una release stabile.
