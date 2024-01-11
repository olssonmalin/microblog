# Studie av Loki

## Vad är Loki?

Loki är ett logg-aggregationsverktyg. [1] Det innebär att det är ett verktyg för att samla loggar från olika källor och
presentera dessa tillsammans på ett anpassningsbart, enhetligt sätt.

Loki består av tre komponenter [2]:

- Promtail
- Loki
- Grafana

Något förenklat är flödet att Promtail hämtar loggar, lägger till noteringar på loggarna och skickar dem vidare till
Loki. Loki fungerar som spindeln i nätet. Promtail skickar sina loggar till en endpoint på Loki-servern som tar emot dem
och sparar dem, oftast i en cloud-lösning men det går även att spara loggarna direkt i filsystemet. En Loki-instans kan
ta emot loggar från flera Promtail-instanser samtidigt. Om man till exempel har ett system med många microservices som
vardera har en Promtail-instans räcker det med en Loki-instans för att samla och persistera loggarna. Loki sköter även
hantering av förfrågningar från administratörer/användare. Dessa förfrågningar kommer från Grafana. I Grafana kan
användaren skicka förfrågningar till Loki och resultatet av dessa förfrågningar (alltså loggarna) går att filtrera,
sortera och så vidare. Det går även att presentera loggarna och generera data om dem. Som ett enkelt exempel kan man få
trendlinjer över förekomsten av ordet "error" i ens loggar.

## Hur man installerar Loki på microblog

Eftersom vi sedan tidigare installerat Grafana kommer vi inte gå igenom hur detta installeras, istället läggs fokus på
hur man installerar Promtail och Loki samt hur man konfigurerar Loki som datakälla i Grafana. Instruktionerna utgår
från att tjänsterna installeras med hjälp av Docker.

### Promtail

För att installera Promtail har vi använt imagen `grafana/promtail:2.5.0`. [3] För att få igång en fungerande container
behöver vi skicka med två saker vid instansiering: volymer och en konfigurationsfil. Den enda volym som behövs för att
Promtail ska starta upp är en volym med just en konfigurationsfil. I vårat fall satte vi upp den volymen som
`./promtail-config.yml:/etc/promtail/promtail-config.yml`. För att promtail ska få tillgång till den data vi vill skicka till Loki lägger vi också in log-filerna från nginx som volym till containern: `/var/log/nginx/:/var/log/nginx/`.

Vi behöver även lägga till ett kommando: `command: --config.file=/etc/promtail/promtail-config.yml`. Detta berättar för Promtail att konfigurationsfilen ska
hämtas från `/etc/promtail/promtail-config.yml`. Vi återkommer till andra volymer senare.

#### Konfiguration

Promtails konfigurationsfil består av flera block och inleds av server-blocket:

```
server:
  http_listen_port: 9080
  grpc_listen_port: 0
```

Promtail exponerar en HTTP-port som exempelvis kan användas för healthchecks. gRPC står för Google Remote Procedure
Calls och är utanför scope av denna studie. Port "0" innebär i alla fall att en slumpmässig port blir allokerad.

```
positions:
  filename: /tmp/positions.yaml
```

För att en Promtail-instans ska kunna hålla koll på vart den senast läste i olika filer behöver tjänsten hålla koll på
var i loggfilerna instansen senast läste. I vårat fall har vi inte valt att persistera positions genom att ha det som en
volym, men det kan (eller bör) man göra i produktionsmiljö så en Promtail-container kan fortsätta där den slutade om den
av någon anledning går ner.

```
clients:
  - url: http://{{ groups['monitoring'][0] | default('localhost') }}:3100/loki/api/v1/push
```

I "clients"-blocket konfigurerar man vilka Loki-instanser som Promtail-instansen ska pusha till. Det går att pusha från
en Promtail-instans till flera Loki-instanser, men det rekommenderas inte utan då bör man istället ha en
Promtail-instans per Loki-instans. [4] I clients-blocket kan man specificera saker som headers och auktorisering, men
för vårat use case räcker det gott med en url. URL:en ska korrespondera med den Loki-instans man vill pusha till.
Default-port för Loki är `3100`.

I vårt fall sätter vi upp promtail på en annan VM än loki startas på för att få tillgång till de loggarn som promtail ska skicka till Loki. Därför använder vi en template i ansible för att skriva ut IP-adressen till Loki. 

Nu kommer vi till the nitty gritty av Promtails config:

```
scrape_configs:
  - job_name: nginx
    static_configs:
      - targets:
          - localhost
        labels:
          job: nginx
          __path__: /var/log/nginx/*.log
```

`scrape_configs` konfigurerar vad Promtail ska läsa för information, detta blir alltså det som skickas vidare till Loki.
Det är en del som händer på ganska få rader här. I vår lösning vill vi hämta loggar från Nginx därför har vi ett jobb som får heta `nginx`. Källar till loggarna defineras i det här fallet med `static_configs` som består utav en lista där varje artikel representerar en källa från vart promtail hämtar data ifrån. Vi klarar oss med en artikel där `target` är satt till `localhost`, med det menas att datan finns att hämta på samma maskin. Därefter defineras `labels` med platsen på datan tillsammans med ett jobb-namn för datan. Med denna konfiguration hämtar Promtail data från filer med filändelsen `.log` som finns på samma maskin i sökväg `/var/log/nginx/`.

Den fulla konfigurationsfilen blir:

```
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://{{ groups['monitoring'][0] | default('localhost') }}:3100/loki/api/v1/push

scrape_configs:
  - job_name: nginx
    static_configs:
      - targets:
          - localhost
        labels:
          job: nginx
          __path__: /var/log/nginx/*.log

```

### Loki

Vi har använt imagen `grafana/loki:2.5.0`[6] för att installera Loki. Konfigurationen för Docker-containern är lik den
för Promtail men enklare. Det behövs bara en volym och ett kommando för konfigurationsfilen, inget mer. Volymen vi
sätter är `./loki-local-config.yml:/etc/loki/local-config.yml`. Kommandot blir följaktligen
`--config.file=/etc/promtail/promtail-config.yml`.

#### Konfiguration

Config-filen för Loki är större än Promtails men innehåller också mer boilerplate. I vårat fall har vi använt en fil
från Loki-repot på Github. [7] Delar är konfigurationsfilen är justerad för vår lösning.  Den fulla konfigurationsfilen är:

```
auth_enabled: false

server:
  http_listen_port: 3100
  # grpc_listen_port: 9096


common:
  path_prefix: /tmp/loki
  storage:
    filesystem:
      chunks_directory: /tmp/loki/chunks
      rules_directory: /tmp/loki/rules
  replication_factor: 1
  instance_addr: 127.0.0.1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb_shipper:
    active_index_directory: /tmp/loki/boltdb-shipper-active
    cache_location: /tmp/loki/boltdb-shipper-cache
    cache_ttl: 24h         # Can be increased for faster performance over longer query periods, uses more disk space
    shared_store: filesystem
  filesystem:
    directory: /tmp/loki/chunks

compactor:
  working_directory: /tmp/loki/boltdb-shipper-compactor
  shared_store: filesystem

limits_config:
  reject_old_samples: true
  reject_old_samples_max_age: 168h

chunk_store_config:
  max_look_back_period: 0s

table_manager:
  retention_deletes_enabled: false
  retention_period: 0s

ruler:
  storage:
    type: local
    local:
      directory: /tmp/loki/rules
  rule_path: /tmp/loki/rules-temp
  alertmanager_url: http://alertmanager:9093
  ring:
    kvstore:
      store: inmemory
  enable_api: true
```

Det viktigaste för oss är att se till att vi har koll på vilken HTTP-port som exponeras. Som tidigare nämnt är `3100`
default vilket även är den port vi använder. Eftersom Loki i grunden bara ska agera som "spindel i nätet" och vi inte är
intresserade av cloudbaserade lösningar för lagring har vi inte lagt någon större vikt vid konfigurationen i övrigt. If
it ain't broke, don't fix it!

### Att koppla Grafana och Loki

Om tidigare steg är korrekt gjorda ska det bara vara att starta igång Grafana så ska Loki finnas bland data sources.

## Hur Loki används (i en dans med Grafana)

Precis som man använder Prometheus för att presentera systeminformation från Prometheus kan man presentera loggar från
Loki. Man kan hämta loggar, filtrera dem och skapa grafer över dem. Ett tips är att använda `Visualizations`-typen
`Logs` där man får ut loggarna i klassisk logg-form. Man kan då filtrera loggarna på intressant information, till
exempel särskilda errors. På det sättet kan man bygga upp en dashboard där man bara får ut verkligt intressanta loggar,
istället för att sikta loggarna manuellt. Man kan även bygga vidare på detta och skapa grafer på förekomsten av
särskilda logghändelser över tid.

## Hur Loki passar in i DevOps

Inom DevOps vill man att information ska vara tillgänglig mellan olika roller, därför är det fördelaktigt att använda sig av log management med Loki som samlar loggar i ett gränssnitt. Ett exempel på det kan vara två utvecklare som jobbar med olika komponenter som interagerar med varandra. Vardera utvecklare har tillgång till loggar som kommer ifrån den del de själva arbetar med men inte varandras. Vid fel i kommunikationen mellan komponenterna ser vardera utvecklare bara den ena sidan, för att få alla loggar mellan komponenterna behöver de få tillgång till båda loggarna. Utan Loki och Promtail kan det betyda mycket administrativt arbete som tar tid och lägger felsökningen på is. Har man istället Loki och Promtail som kan samla loggarna får båda komponenter får båda utvecklarna tillgång till hela kommunikationen. Tillgängligheten gör att felsökning inte fastnar i den administrativa mail-flaskhalsen som äter upp tid för något som snabbt kan lösas med lite mer information om hur felet uppstår. Roller som kan behöva tillgänglighet till loggar men inte har tillgång till logfiler kan se datan utan att behöva få tillgång till logfilerna. En annan aspekt inom devops är lärande och möjligheten att presentera arbete för gruppen, det hjälper Loki med genom att få loggar samlade. Samlingen av loggar ger en bättre överblick och underlättar kommunikation med stakeholders.

Loki eller log management överlag kan även användas för att hjälpa en organisation ta bättre beslut. Om man till exempel innan en sprint upptäcker att man har en del logghändelser som är utanför det normala kan man allokera resurser under sprinten för att undersöka varför dessa dyker upp. Med ett flöde av bra information in till beslutsfattare är det enklare för dem att ta bra beslut. Det här passar in i DevOps eftersom loggar är en resurs som är relativt objektiv. Använder man log management för att upptäcka potentiella eller faktiska risker passar detta väl in i en blameless kultur eftersom man kollar rent konkret på vad risken är snarare än att leta syndabockar. Det ger även en djupare inblick i hur systemen fungerar vilket gör att det blir lättare för samtliga team att se konsekvenser av diverse ändringar i systemet.


## Referenser

[1] Grafana. "Loki". Hämtad 04/01/2023 från https://grafana.com/oss/loki/  
[2] Github. "Grafana Loki". Hämtad 04/01/2023 från https://github.com/grafana/loki  
[3] Docker. "grafana/promtail:2.5.0". Hämtad 04/01/2023
från https://hub.docker.com/layers/grafana/promtail/2.5.0/images/sha256-60dac3460ddf081ea6d795e01d153261ef7fe42604f99e75126e37e26abda67f?context=explore  
[4] Grafana. "Configure Promtail - Supported contents and default values of config.yaml". Hämtad
04/01/2023
från https://grafana.com/docs/loki/latest/send-data/promtail/configuration/#supported-contents-and-default-values-of-configyaml  
[5] Grafana. "Configure Promtail - scrape_configs". Hämtad 05/01/2023
från https://grafana.com/docs/loki/latest/send-data/promtail/configuration/#scrape_configs
[6] Docker. "grafana/loki:2.5.0". Hämtad 05/01/2023
från https://hub.docker.com/layers/grafana/loki/2.5.0/images/sha256-c4f9965d93379a7a69b4d21b07e8544d5005375abeff3727ecd266e527bab9d3?context=explore
[7] Github. "loki/cmd/loki/loki-local-config.yaml". Hämtad 05/01/2023
från https://github.com/grafana/loki/blob/release-2.3/cmd/loki/loki-local-config.yaml
