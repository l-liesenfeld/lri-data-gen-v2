# Motives

_Auto-generated from `data/motive_matrix.json` by `scripts/gen_motives_doc.py`. Edit the JSON, then re-run the script._

The matrix defines 4 categories × 5 motives = 20 motives total. Each motive has an ID (e.g. `A1`, `L3`), a name, and a German description. IDs are the stable reference everything else keys off.

## Strength scale

Every selected motive is configured with a strength between **0.1** and **1.0**. The model receives the numeric value plus this guidance (see `prompts/legacy.txt`):

> Higher strength values (closer to 1.0) mean the motive should be more detectable (though still not explicitly stated). Lower values (closer to 0.0) mean the motive should be more deeply hidden and nuanced or even ambiguous.

Practical anchors:

| Strength | Intent |
|---|---|
| 0.1–0.2 | Barely perceptible — a careful reader might not catch it |
| 0.3–0.5 | Moderate — detectable on close reading |
| 0.6–0.8 | Pronounced — clearly shapes the entry's voice |
| 0.9–1.0 | Dominant — the defining psychological note of the entry |

## Categories

### A — Anschluss (Beziehung)

_Kontakt (meist dyadisch): Horizontal, ohne Zweck, absichtslos, erlebnisorientiert_

| ID | Name | Description |
|---|---|---|
| `A1` | Persönliche Begegnung | (freudig-intuitiver Austausch: intimacy) persönlich werden, sich (auch in der Tiefe) verstehen, mit echtem Interesse füreinander austauschen; tief liebevolles Miteinander; echte persönliche Wärme und Nähe; aufrichtig lieben |
| `A2` | Spaß mit anderen | Extravertierter Kontakt, Unterhaltung, gute Stimmung, Erotik; Spass und Freude miteinander; Leichtigkeit in der Interaktion; geselliges Miteinander; auch oberflächlicher Spass |
| `A3` | Beziehung wiederherstellen | Beziehungsschwierigkeiten (z.B. Zurückweisung) meistern, Verständnis für Leid und Schwäche; Beziehungen nach Konflikten wiederherstellen; Beziehungsschwierigkeiten kreativ mit Gefühl lösen; gesunden Perspektivwechsel zum überwinden von Beziehungsproblemen nutzen |
| `A4` | Harmonie suchen (Affiliation): Nähe | Geborgenheit, Sicherheit finden, geliebt werden, Bindung an Stärkere, Beziehung kontrollieren; einseitig Harmonie suchen; eigene Unstimmitkeit in Gefühlen unterdrücken zugunsten von Harmonie; besonders vernünftig sein in Beziehungen auch gegen das eigene Gefühl |
| `A5` | Alleinsein | Verlassen werden, nicht gemocht werden, einsam sein; ängstliche Beziehungsgestaltung; das Gefühl, allein zu sein |

### L — Leistung (Fähigkeit)

_Gütemaßstab: etwas kann gelingen oder misslingen (besser oder schlechter), Schwieriges selbst meistern_

| ID | Name | Description |
|---|---|---|
| `L1` | Flow | Aufgehen in einer herausfordernden Tätigkeit, Neugier und Interesse, Spaß an der Herausforderung, spielerisches Lernen; Leistungsflow; unerschöpfliche positive Leistungsenergie |
| `L2` | Etwas gut machen | (individueller Gütemaßstab), Schwieriges schaffen, auf ein Ziel fokussiert sein; Zielorientierung; anspruchsvolle Qualitätsorientierung; Exzellenzstreben; Leistungen und Gütestandards übertreffen; Bestleistungen erzielen ist mit positiven Gefühlen verbunden; Gütemaßstäbe übertreffen |
| `L3` | Bewältigung von Misserfolg: Herausforderung | positive Sicht von Schwierigkeiten, aus Fehlern lernen; Flexibilität, eigene mit Teamleistung integrieren; Herausforderungen suchen; Arbeiten nach dem Motto; 'geht nicht, gibt's nicht'; besonders kreativ in der Lösungsfindung bei schwierigen Aufgaben |
| `L4` | Leistungsdruck | Soziale Bezugsnorm: besser sein als andere (ist mit innerem Druck verbunden), Wettkampf, Konkurrenz, ermüdende Anstrengung, nichts falsch machen; druckabhängige Leistungserbringung; Zeit- und Termindruck stimuliert Leistungsbereitschaft |
| `L5` | Misserfolgsfurcht | Wegen eines Misserfolgs hilflos, ratlos, enttäuscht sein; ängstliche Leistungserbringung; Angst, Fehler zu machen; nach Hilfe suchen bei schwierigen Aufgaben; aufgeben bei schwierigen Aufgaben; Angst, dem eigenen Leistungsanspruch nicht genügen |

### M — Macht (Durchsetzen)

_Einfluss auf andere ausüben; vertikaler Kontakt (stärker, schwächer), wirkungs- & zweckorientiert_

| ID | Name | Description |
|---|---|---|
| `M1` | prosoziale Führung | (prosoziale Macht), Selbstausdruck, Rat geben, helfen, Wissen weitergeben, andere schützen, verstehen; positiv Einfluss auf andere ausüben; andere in ihrem Wachstum fördern; anleiten; positive Assoziation mit Verantwortung; Förderung von Sinnhaftigkeit (purpose) |
| `M2` | andere begeistern | Objektbezogener Einfluss, Helfen, Pflegen aus der Situation heraus, andere begeistern, mitreißen; Feedback von anderen benötigt; Lob und Anerkennung brauchen (positive Gefühle durch Lob und Anerkennung); sich wohl auf der Bühne fühlen |
| `M3` | verantwortliche Führung | Trotz Gegenwind: Einfluss nehmen, helfen, integrieren, entscheiden, Freiheit einräumen, Autonomie gewähren; verantwortungsvoll durch Krisen führen; kreative Bewältigung von Schwierigkeiten in der Durchsetzung und Gestaltung; Integration verschiedener Perspektiven bei der Durchsetzung |
| `M4` | Dominanz-inhibiert | Befehlen, strenge Führung, konflikthafte Macht (erkennbar an Negationen), Recht von Macht durch Pflicht; Kampf; Verneinung von Macht und Durchsetzung; Hierarchiedenken; passiv-aggressive Durchsetzung und Behauptung; unterdrückte Gestaltungskraft; Dominanz; Einseitige Strenge |
| `M5` | Ohnmacht | Keinen Einfluss haben, sich unterdrücken; sich schuldig fühlen, unterdrückt werden; Ohnmachtsgefühle; Hilflosigkeit; sich unterordnen; Schwierigkeiten und Durchsetzung passiv vermeiden; Ängstlichkeit in der Durchsetzung |

### F — Freiheit (Selbstsein)

_Selbstwert, Absichtsloses Sein, Selbst-Integration, erlebnisorientiert_

| ID | Name | Description |
|---|---|---|
| `F1` | Selbstvertrauen | Genießen, sich öffnen, offenbaren, Freude an neuer Erfahrung, für sich sein; Selbstvertrauen; explorieren; Freude beim ausprobieren; Freiheit geniessen; voller Freude und Offenheit für Neues |
| `F2` | Status | (bedingtes Selbstvertrauen), Aufmerksamkeit, Anerkennung bekommen, im Mittelpunkt stehen; Status mögen; sich anerkannt fühlen wollen |
| `F3` | Selbstwachstum (SR) | Sicherheit wiedergewinnen, Selbst-Akzeptanz/ Integration von Unangenehmem, Mut zur Wahrheit, Wahllfreiheit, sich neue Erkenntnisse erarbeiten; persönlich wachsen;  herasufordernde persönliche Erfahrungen positiv verwandeln, transformieren; aus Niederschlägen positiv hervorgehen |
| `F4` | Selbstschutz (SK) | Rigide Ich-Grenzen, sich rechtfertigen, Selbstbild durch Vergleich mit anderen, lästern, jemanden nicht mögen, so tun als ob; sich selbst über harte Grenzen schützen; andere nicht an sich heranlassen; Autonomie über Vernunft erzeugen; Autonomie eineitig hart und argumentativ erwirken |
| `F5` | Selbstentwertung | Unsicherheit, Misstrauen, Scham, angeklagt werden, Angst vor Unbekanntem; Nicht gewürdigt werden; sich selbst nicht würdigen; die eigenen Emotionen entwerten; sich selbst entwerten; andere zu eigenen Lasten über sich stellen; eigene Freiräume und Bedürfnisse hinter die von anderen stellen. |

## Levels (reference)

Each motive cell maps to a PSI-theory level (intrinsic approach, extrinsic approach, self-regulated coping, active avoidance, passive avoidance). This metadata is preserved in the matrix but is **not** currently injected into the prompt.

| Key | Name | Description |
|---|---|---|
| `S+` | S+ Positive Stimmung (implizit) aus dem Selbst | Gestaltungskraft, Kreativität, Selbstverständlichkeit |
| `A+` | A+: positiver Anreiz | Aufmerksamkeit ist nach Außen auf ein Objekt gerichtet |
| `S(-)` | S(-): Selbständige Bewältigung | (Selbstdistanzierung) Nennen von Schwierigkeiten, Angst vor einem negativen Ausgang, etc. und kreatives Problemlösen, Flexibilität, Weitblick |
| `A(-)` | A(-): Aktives Vermeiden | Angst vor der Frustration des Motivs wird meist nicht genannt, ist aber an Enge, Kontrollieren, Befolgen, Zielfixierung erkennbar. |
| `A-& A(+)` | A-& A(+): Passive Vermeidung | Nennen eines negativen Ausgangs und negativer Gefühle ohne aktive Bewältigung. |
