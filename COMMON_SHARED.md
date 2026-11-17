# COMMON_SHARED — contract tehnic (de implementat)

**Stare:** componentele shared de mai jos nu sunt implementate. Acest fișier definește responsabilitățile lor, fără a introduce logică de business sau infrastructură declarată automat.

## Pornirea dependențelor (implementată)

`start_dependencies.sh` pornește exclusiv:

| Dependență | Instanță | Port local implicit | Pornire |
| --- | --- | --- | --- |
| PostgreSQL | Server comun | 5432 | Serviciu de sistem |
| RabbitMQ | Broker comun | 5672 | Serviciu de sistem |
| Redis | Server comun | 6379 | Serviciu de sistem |
| Celery | Worker comun, fără taskuri predefinite | — | Fereastră `celery` din sesiunea tmux `ping_patrol` |

Dacă `CELERY_APP` este configurat în `.env`, workerul folosește acea aplicație. În absența lui, este pornită o instanță Celery temporară, fără taskuri, cozi sau reguli de rutare definite de proiect. Scriptul nu instalează pachete și nu configurează automat resursele brokerului ori bazele de date.

## Componente shared — de implementat manual

| Componentă | Responsabilitate comună | Responsabilitate în fiecare microserviciu |
| --- | --- | --- |
| PostgreSQL | Un singur server, cu baze de date distincte | Modele și operații pe baza de date proprie |
| Celery | Configurația comună a aplicației Celery și conexiunile la broker/backend | Definirea taskurilor, a workerilor necesari și asocierea lor la cozi |
| Redis | Conexiune/configurație comună la aceeași instanță Redis | Alegerea utilizării, structurilor de date și cheilor |
| RabbitMQ | Configurația comună a conexiunii, exchange-urilor, cozilor și binding-urilor | Publicarea cu routing key și consumarea mesajelor relevante |
| Python | Un singur `requirements.txt` și un singur mediu virtual la rădăcina proiectului | Importul și utilizarea dependențelor comune |

Servicii cu baze de date separate: `monitoring`, `rules`, `incidents`, `alerts`, `fake_target`. Numele implicite din `common/db/db_init.py` sunt `ping_monitoring`, `ping_rules`, `ping_incidents`, `ping_alerts`, `ping_fake_target`.

## În afara implementării curente

- Modulele Python comune pentru Celery, Redis și RabbitMQ.
- Exchange-uri, cozi, binding-uri, consumatori, taskuri și rute de mesaje.
- Workerii specifici microserviciilor.
- Modificări în modele, baze de date, endpointuri sau logica aplicațiilor.
- Instalarea pachetelor ori modificarea `requirements.txt`.
- Modificarea `start.sh` sau `start_servers.sh`.

**Limita actuală:** se pornesc dependențele; integrarea lor în microservicii rămâne de implementat manual.
