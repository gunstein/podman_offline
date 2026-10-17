# Backlog

Use [the review guide](docs/REVIEW_GUIDE.md) for product contracts, lifecycle
review, evidence levels and the required understandability check. Follow
[AGENTS.md](AGENTS.md) when implementing or reviewing these tasks.

Planned work, not implemented behavior. Each item requires separate implementation
and verification. Item numbers are stable references, not execution priority.
The recommended implementation sequence through item 1 is complete. Remaining
items retain their individual scopes below; agree the next priority separately.

Implemented: test baseline (item 10, commit `511099e`) and rename/separate
platform bundle (item 8), separate Identity bundle (item 9, 0.4.0), and credential
path cleanup (item 12, 0.4.1; [verification](acceptance/CREDENTIAL-PATHS.md)), and
retry-safe lifecycle operations (item 13, 0.4.2; [verification](acceptance/RETRY-SAFETY.md)),
and deploy package refactor (item 1, 0.4.3; [verification](acceptance/DEPLOY-REFACTOR.md)),
and app credential delivery cleanup (item 14, 0.4.4; [verification](acceptance/CREDENTIAL-DELIVERY.md)),
and removal of obsolete layout checks (item 15, 0.4.5; [verification](acceptance/LEGACY-CHECK-CLEANUP.md)),
and unified file-source declarations (item 16, 0.4.6; [verification](acceptance/FILE-SOURCES.md)),
and stock nginx with YAML proxy config (item 18, 0.4.7; [verification](acceptance/NGINX-YAML.md)),
and app1 database schema init (item 17, 0.4.8; [verification](acceptance/APP1-INIT.md)).
Declarative components (item 20, 0.4.9; [verification](acceptance/DECLARATIVE-COMPONENTS.md))
are implemented locally; real acceptance runs are pending.
See [Identity verification](acceptance/IDENTITY-SPLIT.md). Lab verification remains pending; it does not
block the next implementation step. Run the historical upgrade at `511099e` and
current platform/lifecycle scenarios separately; see [platform verification](acceptance/PLATFORM-RENAME.md).

Item 15 removes historical layout refusal checks; the earlier task descriptions
and reports retain their original scope and are not current requirements.

The full agent task descriptions for items 8, 9 and 10 are preserved below, with
heading levels adjusted for this document. The later clarification in item 9
supersedes item 8's bundled-platform assumptions: platform is to be a separate
bundle with explicit dependencies, and app bundles must not embed it. Do not
reintroduce the older bundle model while renaming. Inspect the actual repository
baseline before implementation; these tasks are not claims of completed work.

The refactor must preserve the behavior and naming established by items 8 and 9;
its original core terminology below is historical scope, not an instruction to
restore core or merge Identity back into platform.

## 10. Supplement test coverage before structural changes

Status: implemented locally at `511099e`; historical lab verification pending. Item 8 proceeded with explicit user authorization.
See [test baseline and lab command](acceptance/TEST-BASELINE.md) for coverage,
results and the retained 0.2.0 upgrade gate. The original task is preserved below.
This task includes the retained 0.2.0 upgrade scenario already tracked in item 5;
implement it once and cross-reference its evidence rather than duplicating it.

Suppler testdekningen i `gunstein/podman_offline` før den planlagte refaktoreringen av deploy-koden.

Målet er å etablere en tydelig, testet baseline for eksisterende oppførsel. Dette er en avgrenset testoppgave, ikke selve refaktoreringen.

### 1. Kartlegg eksisterende dekning og kjør baseline

Les dagens kode, tester og verifikasjonsrapporter. Kontroller særlig:

- `tests/`
- `acceptance/`
- `deploy.py`
- `bundle.py`
- Rotkommandoene og bundle-innholdet.

Kjør eksisterende produkt- og acceptance-harness-tester før endringer. Registrer commit og resultater.

Gjenbruk eksisterende fixtures og testverktøy. Ikke dupliser tester som allerede dekker kravene nedenfor.

### 2. Test reell oppgradering fra 0.2.0

Legg til et målrettet acceptance-scenario som oppgraderer en faktisk 0.2.0-installasjon til dagens versjon.

Bruk en identifisert historisk commit for gammel kode og gamle images. Ikke simuler gammel release ved bare å endre `VERSION` i dagens kode.

Scenario:

1. Bygg og installer gammel app1/core og app2.
2. Opprett brukerdata gjennom eksisterende e2e-/markørmekanisme.
3. Registrer eksisterende versjoner, config, credential-filer, databasevolumer og relevante tjenesteobservasjoner.
4. Følg dagens dokumenterte manuelle oppgraderingssteg: legg til nødvendige DB-felter og `GENERATED_SECRETS`-oppføringer i persistent config.
5. Overfør og installer ny app1/core-bundle.
6. Verifiser at app1/core fungerer, og at gammel app2 fortsatt fungerer uten utilsiktede endringer.
7. Oppgrader deretter app2 og verifiser hele installasjonen.

Kontroller spesielt:

- Eksisterende databasepassord beholdes byte-for-byte.
- Databasevolumer beholdes, og eksisterende brukerdata er tilgjengelige.
- Persistent config endres bare gjennom de eksplisitte operatørstegene.
- Ingen credentials regenereres eller databasebrukere endres automatisk.
- App1-oppgraderingen ikke endrer app2s tjeneste, versjon, config eller credentials.
- Innlogging og databaseoperasjoner fungerer etter hvert oppgraderingstrinn.
- Trust for gammel release fjernes først etter vellykket verifikasjon, uten å berøre sibling-bundles.

Test også at manglende nødvendige configtillegg avvises før image-operasjoner og endringer i installert tilstand. Dette kan dekkes av en fokusert lokal test dersom eksisterende dekning er tilstrekkelig.

Hold scenarioet avgrenset. Ikke gjenta hele matrisen av reboot-, crash- og hang-tester hvis disse allerede dekkes separat.

### 3. Lås feiloppførselen under installasjon

Undersøk eksisterende dekning og suppler for:

- Feil under `podman load`.
- Feil eller manglende image ved `podman image exists`.
- Feil ved restart eller `is-active` for en berørt systemd-tjeneste.

Bruk eksisterende komponentinstallasjon som utgangspunkt.

Test relevante observasjoner:

- Persistent config og credentials.
- Importarkiver.
- Route- og OIDC-klientregistreringer.
- Quadlet- og YAML-filer.
- Versjonsmarkører.
- Hvilke tjenester som er forsøkt restartet, og i hvilken rekkefølge.
- At upåvirkede sibling-komponenter beholdes.

Skille mellom feil før og etter at installasjonen begynner å endre tilstand. Ikke anta at installasjon er atomisk eller at rollback allerede finnes.

Ved servicefeil skal testen beskrive den faktiske delvis gjennomførte tilstanden og kontrollere at videre steg stopper, og at versjonsmarkører ikke feilaktig hevder en fullført installasjon.

Bruk konkrete feilscenarioer fremfor tester som bare gjentar interne funksjonskall.

Hvis du finner en eksisterende feil, dokumenter den med en fokusert reproduksjon. Ikke lås en kjent feil som ønsket oppførsel eller gjør urelaterte produktendringer uten å synliggjøre dem.

### 4. Test rotkommandoer fra en annen arbeidsmappe

Legg til integrasjonstester som starter de faktiske wrapper-scriptene fra en arbeidsmappe utenfor checkout/release:

```text
./deploy prepare
./deploy init-config <component>
./deploy install
./deploy uninstall
./build-bundle.sh
```

Bruk absolutt sti til wrapperen i testen.

Test kommandoene i riktig kontekst:

- `prepare` og bundling fra kildekoden.
- `init-config`, `install` og `uninstall` fra en utpakket bundle.

Verifiser at ressursstier og configvalg fungerer uavhengig av callerens arbeidsmappe, og at output ikke utilsiktet skrives dit.

Bruk isolerte midlertidige mapper og eksisterende stubs for Podman/systemd der det er hensiktsmessig. Ikke kjør produksjonskommandoer mot utviklerens virkelige hjem eller containermiljø.

Der realistisk testing krever tjenestebruker, brukerhjem og systemd-runtime, legg kontrollen i det eksisterende autoriserte labscenarioet fremfor å bygge et komplisert nytt mock-rammeverk.

### 5. Avgrensning

Ikke implementer:

- Oppdeling i `deployment/`-pakken.
- Ny CLI-arkitektur.
- Directory trust for fapolicyd.
- Passordrotasjon.
- Automatisk config- eller databasemigrering.
- Ny rollback-mekanisme.

Tester for den kommende pakkestrukturen, `python -B`, bytecode-ekskludering og directory trust hører til refaktoreringsoppgaven.

Behold eksisterende sikkerhetskontroller og testassertions. Ikke svekk dem for å få nye scenarioer til å passere.

### 6. Verifikasjon

Kjør etter endringene:

- Alle produkttester.
- Alle acceptance-harness-tester.
- Relevante ruff-, format-, pyright-, vermin- og shellcheck-kontroller med prosjektets eksisterende oppsett.

Behold Python 3.6-kompatibilitet for host-verktøy og produkttester.

Kjør det nye reelle oppgraderingsscenarioet dersom det etablerte labmiljøet er tilgjengelig og kjøring er autorisert. Ikke reset eller endre andre miljøer.

Skill tydelig mellom lokale tester, harness-tester og faktiske målmaskinkjøringer. Hvis labkjøring ikke er mulig, implementer scenarioet og rapporter at oppgraderingen fortsatt ikke er operasjonelt verifisert.

### 7. Leveranse

Rapporter kort:

1. Baseline-commit og testresultater før endringer.
2. Hvilken dekning som allerede fantes.
3. Nye tester og hvilke konkrete feil de beskytter mot.
4. Historisk og ny revision brukt i upgrade-scenarioet.
5. Testresultater, inkludert faktisk labkjøring.
6. Eventuelle oppdagede produktfeil og verifikasjonshull.
7. Om baseline er tilstrekkelig til å starte refaktoreringen.

Oppdater relevant testdokumentasjon med garantiene og begrensningene.

Foretrekk noen få sterke tester fremfor mange overlappende tester.

## 1. Deploy maintainability refactor

Status: implemented in 0.4.3 after items 10, 8, 9, 12 and 13. Local checks passed;
real directory trust remains unverified on the target. See [verification](acceptance/DEPLOY-REFACTOR.md).
No existing installation requires migration: this implementation adds no migration,
old-module fallback or compatibility layer. The original task follows.

Refactor the deploy implementation for maintainability without redesigning the architecture or changing behavior.

Goal: a medium-experienced developer with some Python knowledge and little familiarity with this project should be able to understand the install/upgrade/uninstall flow quickly.

Keep the root commands unchanged:

- `./deploy prepare`
- `./deploy install`
- `./deploy uninstall`
- `./build-bundle.sh`

Move deploy internals into a small Python package, roughly:

```text
deployment/
  __init__.py
  __main__.py
  cli.py
  deploy.py
  render.py
```

Keep `./deploy` as the stable entrypoint and run Python with `-B`, e.g. `python3 -B -m deployment`, so trusted release code does not create `.pyc`/`__pycache__`. Preserve invocation from outside the release directory as well.

Responsibilities:

- `render.py`: config/YAML loading, placeholders, generated-secret helpers, SECRET_FILES/VOLUME_FILES, Secret/PVC generation, manifest validation/rendering.
- `deploy.py`: production environment, component/bundle selection, VERSION/CORE_VERSION logic, registrations/routes/OIDC clients, image load/verify, Quadlet/systemd, install/uninstall lifecycle.
- `cli.py`: argument handling and error reporting.
- `__main__.py`: minimal delegation to the CLI.
- Do not introduce unnecessary classes or framework abstractions.

Important simplifications:

- Make the main install flow easy to read: determine plan → stage registrations → render → load/verify images → apply registrations → write Quadlet/YAML → restart affected services → write version markers.
- The main install function should read as that lifecycle sequence. Helper names should make persistent writes and service restarts obvious.
- Avoid surprising side effects in `render()` where practical; make persistent generated-secret creation explicit.
- Split `registration_stage()` if that improves readability.
- Reduce duplicated component truth between `bundles.yaml` and hardcoded Python where this can be done simply, but do not build a generic plugin system.
- Keep standalone manifest support used by examples/tests, but isolate it from the main component lifecycle. Do not remove supported examples as part of this refactor.

Behavior preservation:

- Preserve existing prepare/install/upgrade/uninstall behavior, including component isolation, core version rules, restart decisions, persistent state retention and explicit data deletion.
- Preserve validation order and failure semantics, including which persistent files may have changed when an operation fails.
- Explicit generated-secret creation must not happen earlier than today.
- Treat the lifecycle sequence above as a readability goal, not permission to reorder safety checks.
- Do not silently fix unrelated bugs. Report discovered issues separately.

fapolicyd:

- Support multiple Python files using directory trust.
- Trust only `<release>/deployment/` recursively with the existing per-bundle trust file.
- On upgrade, remove the old release’s `deployment/` trust entry after the new release has been verified successfully.
- Do not trust the whole release and do not add new allow/crun/memfd rules.
- Keep SELinux/fapolicyd hardening unchanged.
- Update trust verification and cleanup to match the directory-based approach.

Bundling:

- Keep `bundle.py` mostly as-is.
- Include `deployment/` in offline bundles.
- Never include `.pyc`, `__pycache__`, generated secrets or private state.
- Keep all checksum guarantees.
- Ensure imports and resource paths work both from the source checkout and from an unpacked offline bundle.

Tests/docs:

- Adapt existing tests; preserve Python 3.6 compatibility.
- Run product tests, acceptance-framework tests, ruff, format check, pyright, vermin and shellcheck.
- Add focused regressions for the root entrypoint, package contents in bundles, no bytecode files, unchanged prepare/install/uninstall behavior, and directory-based fapolicyd trust/upgrade cleanup.
- Check that failed validation or image verification preserves existing deployed state as before.
- Update README/trust instructions and stale monolithic service names.
- Add a short `ARCHITECTURE.md` explaining module responsibilities, the lifecycle flow, shared core versus independent components, and persistent state versus disposable release files.
- Report acceptance-framework tests separately from actual target-host acceptance runs. If no lab is available, state explicitly that directory trust remains unverified on the target.
- If a required check cannot run, report the reason rather than treating it as passed.

Prefer a mechanical move with passing tests first, followed by focused readability improvements. Prefer simpler code over more generic code.

Do the refactor, run the checks, and report:

1. New structure.
2. What moved where.
3. Any intentional or discovered behavior differences, including the required fapolicyd trust change.
4. Test and static-check results, clearly distinguishing local checks from target-host verification.
5. Anything intentionally left for later, including unrelated issues discovered during the work.

## 2. PostgreSQL password rotation

Status: planned; separate from the deploy refactor.

- Define an explicit operator-controlled procedure coordinating the database role
  password, persistent secret file and running clients for core/app1/app2.
- Use the existing ownership, file paths, Secret keys and volume mapping in
  [README.md](README.md#postgresql-configuration-and-credentials).
- Define failure handling and verification before selecting a mechanism. Verify
  authentication after rotation and retention of database data.
- Keep session keys, demo-user passwords, OIDC keys and certificates outside this
  database-specific procedure. Never rotate implicitly during install or upgrade.

## 3. Database backup and credential recovery procedures

Status: planned; separate from password rotation.

- Document and exercise coordinated backup/restore of database volumes and their
  persistent password files, including private permissions.
- Define an explicit recovery procedure for missing credentials or a mismatched
  database password, with operator prerequisites and authentication checks.
- Preserve refusal to generate a replacement password when database state exists.
  Do not delete/reinitialize volumes or assume that changing the secret file
  changes the PostgreSQL role password.
- Keep credentials and connection strings out of logs and acceptance evidence.

## 4. Migration from retained monolithic 0.1.x installations

Status: superseded by the clarification in item 15: no existing installations
require migration. The original proposal below is retained as history, not
planned implementation work.

- Inventory old services, config, credentials and database volumes before defining
  a migration to core/app1/app2/help.
- Define backup, identity/data mapping, service transition and recovery steps.
- Verify retained application data and credentials on a real migration fixture.
- Do not add automatic migration or destructive cleanup to normal upgrades.

## 5. Close documented runtime verification gaps

Status: planned verification work; current evidence remains unchanged.
The retained 0.2.0 upgrade scenario below is implemented as part of item 10;
run the [focused lab scenario](acceptance/TEST-BASELINE.md#run-the-historical-upgrade-in-the-lab)
and cross-reference its evidence here rather than implementing it again.

- Run a full retained 0.2.0 → 0.2.1 upgrade with the documented manual DB config
  additions, verifying existing credentials, volumes and sibling state.
  Prioritize this before upgrading an important retained installation. Start with
  the old release's real config, initialized database volumes and credentials;
  apply only the documented manual additions, then install the new images and
  verify authentication, CRUD, persistent data and unaffected siblings. Existing
  legacy-password fixtures do not replace this end-to-end upgrade scenario.
- Verify supported Podman versions beyond the currently tested 5.8.2 before
  claiming runtime coverage for them.
- Verify localized PostgreSQL authentication diagnostics, preserving the distinction
  between authentication refusal and DNS/network failures.
- Run host tooling on an actual Python 3.6 interpreter if a suitable environment
  is available; current Python 3.6 compatibility evidence is static.
- Report local/harness checks separately from actual target-machine results.

Source and existing evidence: [DATABASE-VERIFICATION.md](acceptance/DATABASE-VERIFICATION.md#limits-and-deferred-work).

## 6. Runtime connection strings for existing .NET images

Status: delivery scope decision required; Identity demonstrates the interface,
but does not provide integration for unmodified application images.

- Decide whether existing production images must run without application source
  changes. The current `DatabaseEnvironment.cs` runs inside Identity and requires
  application integration; it is not a reusable external launcher.
- If required, provide a small in-image launcher or equivalent derived-image
  integration that builds `ConnectionStrings__Default` at runtime using a proper
  connection-string builder, then starts the unchanged application.
- Preserve the existing config/Secret model, special-character handling, password
  file semantics, offline packaging and signal/exit-code behavior. Do not render
  credentials into YAML, write connection strings to disk or add host-trust rules.
- Verify a real unchanged target application consumes the environment value and
  connects with the correct secret, rejects an incorrect secret, and has no old
  file-based fallback. Report actual tested image and Podman versions.

## 7. PostgreSQL preflight manifest compatibility

Status: follow up when adding another PostgreSQL image or mount layout.

- Document and test the current assumptions in `database_preflight()`, including
  the `/var/lib/postgresql/data` mount and explicit Secret `items` mapping.
- Before supporting a different layout, ensure the guard identifies its actual
  password source and persistent database volume. Unsupported layouts must fail
  clearly before secret generation or persistent changes.
- Add focused regressions for each newly supported layout. Keep database-state
  checks in the lifecycle layer and avoid a generic PostgreSQL framework.

Review source for items 6–7 and the expanded upgrade scenario: static code review
of `improvements-0-2` through `87f4e98`. These are follow-up requirements and
verification gaps, not evidence of completed runtime support.

## 8. Rename core to platform

Status: implemented locally in 0.3.0; fresh platform/refusal lab verification pending.
The user explicitly selected a separate platform bundle for this step. Platform
still contains Identity until item 9. The original task below is retained;
[PLATFORM-RENAME.md](acceptance/PLATFORM-RENAME.md) describes the delivered model,
compatibility boundary and checks. The later separate-bundle clarification takes
precedence over the original embedded-platform assumptions in this task.

Gi den delte komponenten `core` navnet `platform` i `gunstein/podman_offline`.

Dette er en avgrenset navneendring. Behold arkitektur, funksjonalitet, sikkerhetskontroller og komponentisolasjon. Ikke gjennomfør modulrefaktoreringen samtidig.

### 1. Mål og begrepsbruk

Bruk `platform` om den delte komponenten som inneholder Identity, identitetsdatabasen og HTTPS-proxyen.

App1, app2 og help skal fortsatt ha samme avhengighet til denne komponenten som de i dag har til core.

Omdøpingen skal være konsekvent i aktiv kode, konfigurasjon, manifester, tester og dokumentasjon.

### 2. Kartlegg alle berørte navn før endringer

Undersøk blant annet:

- `components/core/`.
- `CORE_VERSION`.
- Bundle-definisjoner og descriptors.
- Funksjoner, variabler og feilmeldinger.
- Persistent komponentmappe og installed-markør.
- Quadlet-/systemd-navn.
- Pod-, Secret-, PVC- og ConfigMap-navn.
- Hostnames og `DB_HOST`.
- Registrerings- og importarkivnavn.
- Sertifikatgenerering og tilhørende filstier.
- Dev-script, acceptance-script og fixtures.
- README, verifikasjonsrapporter og backlog.

Skill mellom navn som tilhører komponenten, eksterne begreper og historiske referanser. Ikke bruk ukritisk global søk-og-erstatt.

### 3. Ønsket navngivning

Bruk blant annet:

```text
components/platform/
PLATFORM_VERSION

/var/lib/myproduct/platform/config.yaml
/var/lib/myproduct/installed/platform

myproduct-platform.service
myproduct-platform.kube
myproduct-platform.yaml
```

Ressurser med komponentprefikset `core-` skal få `platform-`, eksempelvis:

```text
platform-identity
platform-identity-postgres
platform-identity-data
platform-database-password
platform-routes
platform-clients
```

Oppdater alle referanser til de omdøpte ressursene.

Behold navn som ikke trenger å endres:

- Produktnavnet `myproduct`.
- Det delte nettverket `myproduct`.
- App1/app2/help og deres egne ressurser.
- Offentlige URL-paths som `/identity/`, `/app1/`, `/app2/` og `/help/`.
- Databasebrukere og databasenavn, eksempelvis `identity`.
- OIDC-klient-ID-er og scopes.
- Image-repositorier som ikke inneholder komponentnavnet.

Ikke endre credentials eller sertifikatinnhold bare fordi komponenten får nytt navn.

### 4. Bundle-modell og kommandoer

Bundle-modellen skal bli:

```yaml
app1: [platform, app1]
app2: [platform, app2]
help: [help]
```

Behold de tre eksisterende bundle-typene og deres filnavnmønstre:

```text
myproduct-app1-<version>-offline.tar.gz
myproduct-app2-<version>-offline.tar.gz
myproduct-help-<version>-offline.tar.gz
```

Det skal ikke opprettes en separat platform-bundle.

Behold rotkommandoene. Oppdater komponentargumentene:

```sh
./deploy init-config platform
./deploy uninstall platform
./deploy uninstall platform --delete-data
```

Gamle `core`-argumenter skal ikke utføre utilsiktede operasjoner. Gi en tydelig melding om nytt navn dersom de brukes.

Platform skal fortsatt:

- Installeres sammen med første app.
- Beholdes ved lik platform-versjon, med eksisterende regler for registreringsendringer og restart.
- Oppgraderes ved nyere platform-versjon.
- Avvise nedgradering.
- Ikke kunne avinstalleres mens app1, app2 eller help krever den.

### 5. Eksisterende installasjoner og migrering

Omdøpingen berører persistente ressursnavn. Den må ikke føre til at en eksisterende database erstattes av et nytt tomt volum uten at operatøren forstår det.

Denne oppgaven gir ikke tillatelse til å slette, resette eller migrere eksisterende produksjonsstate automatisk.

Bruk følgende avgrensning:

- Implementer den nye navngivningen for nye installasjoner.
- Ikke implementer automatisk migrering fra `core` til `platform`.
- Oppdag gammel core-layout og avvis operasjoner som ellers kan opprette en parallell platform-installasjon eller påvirke gammel state.
- Feil før generering av nye secrets, image-operasjoner, skriving av installert config/registreringer eller endringer i tjenester.
- Gi en tydelig melding om at gammel installasjon krever en separat migreringsprosedyre eller en eksplisitt ny installasjon.
- Avvis også blandet core/platform-state fremfor å gjette hvilken som er autoritativ.

Kontrollen må ikke bare bruke installed-markøren. Undersøk relevante gamle config-/tjenestefiler og persistente databasevolumer, siden avinstallasjon kan ha beholdt data.

Hold kontrollen konkret og avgrenset til produktets kjente ressurser. Feil ved nødvendige tilstandskontroller skal ikke tolkes som fravær.

Behold gamle filer og volumer urørt ved avvisning. Ikke legg til en automatisk «cleanup»-funksjon.

Dokumenter kompatibilitetsbruddet tydelig. Eksisterende installasjoner skal fortsatt kunne administreres med sin tidligere release.

### 6. Versjonering

Ikke publiser endringen under samme releaseversjon som eksisterende layout.

Oppdater `VERSION` og den nye `PLATFORM_VERSION` i tråd med prosjektets versjoneringspraksis, og forklar at navneendringen påvirker oppgraderingskompatibilitet.

Ikke endre image-tags dersom image-innholdet er uendret. Hvis image-innhold faktisk må endres, bruk nye tags og behold prinsippet om immutable release-tags.

### 7. Tester

Oppdater eksisterende tester til den nye navngivningen uten å svekke assertions.

Verifiser minst:

- Korrekte platform-prefikser og referanser i rendret YAML.
- Initialisering av platform-config.
- App-config arver de riktige felles verdiene fra platform.
- App1 og app2 kan hver være første installerte app.
- Help alene avvises.
- Lik, nyere og eldre `PLATFORM_VERSION` håndteres som før.
- Help-only og app-only upgrade beholder upåvirkede komponenter.
- Databasepassord og databasevolumer er koblet korrekt.
- Platform-uninstall blokkeres når dependenter finnes.
- `--delete-data` bare retter seg mot valgt komponents ressurser.
- Bundle-innhold, image-utvalg og checksums er korrekte.
- Gammel core-layout og blandet layout avvises uten endringer.
- Gamle core-databasevolumer oppdages selv om installed-markøren mangler.
- Feil ved tilstandskontroll gir kontrollert avvisning.

Behold historiske fixtures og historiske release-kilder når de faktisk skal representere gammel kode.

En test som tidligere oppgraderte fra en core-basert release kan ikke bare gis nye navn og fortsatt hevde å teste den historiske oppgraderingen. Behold relevant historisk dekning, men test tydelig avvisning ved denne nye kompatibilitetsgrensen.

### 8. Dokumentasjon og opprydding

Oppdater aktive beskrivelser, kommandoer, filstier og diagrammer til `platform`.

Søk gjennom hele repoet etter relevante forekomster av `core`, `CORE_VERSION` og `core-`.

Forklar bevisst beholdte forekomster, eksempelvis:

- Gammel-layout-deteksjon.
- Historiske fixtures.
- Tidligere verifikasjonsrapporter.
- Dokumenterte migreringsbegrensninger.

Ikke omskriv gamle testresultater eller historisk evidence slik at det ser ut som de ble kjørt med platform-layout.

Oppdater backlog med eventuell fremtidig migreringsoppgave. Ikke bland den inn i modulrefaktoreringen.

### 9. Verifikasjon og rapport

Kjør:

- Alle produkttester.
- Alle acceptance-harness-tester.
- Relevante ruff-, format-, pyright-, vermin- og shellcheck-kontroller.

Behold Python 3.6-kompatibilitet for host-verktøyene.

Kjør relevante nye installasjons- og livssyklusscenarioer i det etablerte labmiljøet dersom dette er tilgjengelig og autorisert. Ikke slett eksisterende state eller reset andre miljøer.

Skill mellom lokale tester, harness-tester og faktiske målmaskinkjøringer.

Rapporter:

1. Hvilke navn og filer som er endret.
2. Hvilke navn som bevisst er beholdt.
3. Hvordan gammel og blandet layout oppdages og avvises.
4. Konsekvensen for eksisterende installasjoner.
5. Versjonsendringer.
6. Testresultater og verifikasjonshull.
7. Arbeid som er utsatt, særlig eventuell migrering.

Foretrekk enkel og konsekvent navngivning fremfor et generisk alias- eller kompatibilitetsrammeverk.

## 9. Extract Identity into a separate component and bundle

Status: implemented in 0.4.0; real lab verification pending. Platform and Identity are separate bundles with explicit dependencies. See [Identity verification](acceptance/IDENTITY-SPLIT.md). The original task follows.

Skill Identity ut av `platform` som en egen komponent med en egen separat offline-bundle i `gunstein/podman_offline`.

Dette er en funksjonell oppdeling som skal gjøres før den planlagte modulrefaktoreringen. Ikke gjennomfør modulrefaktoreringen samtidig.

### 1. Undersøk dagens løsning først

Les gjeldende kode, bundle-definisjoner, avhengighetsmodell, tester og dokumentasjon.

Platform er allerede ment som en separat bundle. Ikke ta utgangspunkt i den tidligere modellen hvor app-bundler inkluderte core/platform.

Gjenbruk eksisterende mekanismer for komponenter, bundles, versjoner og avhengigheter. Ikke innfør et parallelt system eller et generisk plugin-rammeverk.

Registrer baseline-commit og kjør eksisterende produkt- og acceptance-harness-tester før endringer.

### 2. Ønsket ansvarsdeling

Etter oppdelingen skal:

| Komponent | Ansvar |
|---|---|
| `platform` | HTTPS-proxy, proxyens TLS-materiale og offentlige ruteregistreringer |
| `identity` | IdentityServer, identitetsdatabase, databasepassord, signeringsmateriale, Data Protection-state, demobrukere og OIDC-klientregistreringer |
| `app1` | App1, egen database og egne credentials |
| `app2` | App2, egen database og egne credentials |
| `help` | Hjelpeinnhold og egen ruteregistrering |

Behold eksisterende eierskap og sikre livssyklusregler for delt nettverk og eventuell felles demo-CA. Ikke slett eller regenerer felles materiale som følge av oppdelingen.

Kartlegg alle eksisterende ressurser og filer før flytting, slik at ingen persistent state blir glemt.

### 3. Separate bundles og eksplisitte avhengigheter

Bruk følgende logiske modell:

| Bundle | Innhold | Avhengigheter |
|---|---|---|
| `platform` | Platform-komponenten | Ingen |
| `identity` | Identity-komponenten | Platform |
| `app1` | App1-komponenten | Platform og identity |
| `app2` | App2-komponenten | Platform og identity |
| `help` | Help-komponenten | Platform |

Hver bundle skal bare inneholde egne komponentressurser og nødvendige images, i tillegg til felles deploy-kode og nødvendige metadata/defaults.

App-bundler skal ikke inkludere eller installere platform/identity automatisk. Identity-bundlen skal ikke inkludere platform.

Manglende avhengighet skal gi en tydelig feil. Ikke forsøk nettverksnedlasting eller automatisk installasjon fra andre release-mapper.

Oppdater eksisterende bundle-bygging slik at alle definerte bundles produseres, inkludert separat identity-bundle, med prosjektets etablerte filnavnmønster.

### 4. Versjoner og kompatibilitet

Identity skal kunne versjoneres og oppgraderes uavhengig av platform og appene.

Bruk eksisterende versjoneringsmodell. Hvis denne bruker separate versjonsfiler, innfør en tilsvarende `IDENTITY_VERSION`. Ikke opprett et nytt versjoneringssystem hvis repoet allerede har en egnet modell.

Avhengigheter skal ha eksplisitte, dokumenterte versjonskrav. Gjenbruk eksisterende syntaks og sammenligningsregler. Hvis slike krav ikke finnes, innfør den minste mekanismen som dekker behovet, og begrunn valget.

Valider:

- At avhengighetene er installert.
- At deres versjoner tilfredsstiller innkommende bundles krav.
- At oppgradering av platform eller identity fortsatt tilfredsstiller kravene til installerte dependenter.

Oppbevar nødvendig avhengighetsmetadata som installert state. Kontrollene skal ikke avhenge av at gamle release-mapper fortsatt finnes.

Ikke anta kompatibilitet bare fordi en versjon er nyere.

Behold eksisterende regler for reinstallasjon og nedgradering der de fortsatt er relevante. Dokumenter eventuelle nødvendige endringer.

Alle avhengighets- og versjonsavvisninger skal skje før secret-generering, image-load, skriving av registreringer/tjenestefiler eller restart.

### 5. Skill ruteregistreringer fra OIDC-klientregistreringer

I dagens samlede løsning kan begge registreringstypene påvirke samme komponent. Etter oppdelingen skal eierskapet være tydelig:

- Platform konsumerer offentlige ruter.
- Identity konsumerer offentlige OIDC-klientregistreringer.
- Appene eier sine private klientnøkler og leverer bare offentlig klientmetadata og sertifikat til identity.
- Identity registrerer sin egen offentlige route hos platform.
- Help registrerer bare en route hos platform.

Behold indeksmekanismen som hindrer at gamle filer i importvolumer holder fjernede ruter eller klienter aktive.

Restartbeslutninger skal være separate:

| Endring | Forventet påvirkning |
|---|---|
| Bare app-route endres | Platform oppdateres/restartes |
| Bare OIDC-klientregistrering endres | Identity oppdateres/restartes |
| Begge endres | Begge berørte komponenter oppdateres/restartes |
| Ingen registrering endres | Ingen unødvendig restart av platform/identity |
| Help-route endres | Platform påvirkes, identity beholdes |
| Identity oppgraderes uten endret offentlig route | Identity påvirkes, platform beholdes |

Appenes containere skal ikke restartes bare fordi platform eller identity restartes. Et kort avbrudd i tilgjengelighet eller innlogging er noe annet enn restart av appene.

Ikke legg til nye registreringskommandoer hvis eksisterende installasjonsflyt kan håndtere dette tydelig.

### 6. Behold den offentlige innloggingskontrakten

Oppdelingen skal ikke samtidig endre:

- `/identity/`.
- Offentlig issuer-URL.
- Appenes klient-ID-er og scopes.
- Redirect-URI-er.
- `/app1/`, `/app2/` og `/help/`.
- Appenes cookie-navn og paths.

Oppdater interne hostnames og upstream-referanser der det er nødvendig.

Platform skal kunne kjøre og betjene help uten at identity er installert. Proxykonfigurasjonen må ikke kreve at en fraværende identity-tjeneste kan DNS-resolves ved oppstart.

Verifiser fortsatt delt innlogging mellom app1 og app2.

### 7. Config, secrets og database

Identity skal få egen komponentconfig og persistent mappe:

```text
components/identity/config.defaults.yaml
/var/lib/myproduct/identity/config.yaml
```

Følg eksisterende configmodell:

- Defaults brukes ved initialisering og dev.
- Produksjon bruker autoritativ persistent komponentconfig.
- Upgrade overskriver ikke eksisterende config.

Identity skal arve relevante felles verdier fra installert platform ved config-initialisering, etter samme etablerte prinsipp som øvrige dependenter.

Flytt identity-spesifikke DB-innstillinger, Secret-/volumdefinisjoner og generated-secret-oppføringer ut av platform.

Behold:

- Én persistent kilde for hvert databasepassord.
- Samsvar mellom PostgreSQL-server og klient.
- Beskyttelse mot å generere nytt passord når database-state allerede finnes.
- Runtime-bygging av `ConnectionStrings__Default`.
- Korrekt escaping og sikker feilhåndtering.
- Eksisterende databasebruker og databasenavn hvis det ikke finnes en nødvendig grunn til å endre dem.

Ikke innfør passordrotasjon, databaseprivilegium-endringer eller schema-migrering i denne oppgaven.

### 8. Eksisterende installasjoner: ikke migrer automatisk

Oppdelingen berører persistent identitetsdatabase, credentials, signeringsnøkler, Data Protection-state og klientregistreringer.

Denne oppgaven gir ikke tillatelse til automatisk flytting, sletting eller reinitialisering av eksisterende installert state.

Implementer ny layout for nye installasjoner. Oppdag eksisterende layout hvor identity fortsatt inngår i platform, og avvis inkompatibel installasjon/oppgradering før endringer.

Kontrollen skal også håndtere:

- Beholdte databasevolumer uten installed-markør.
- Blandet gammel og ny layout.
- Delvis eksisterende credentials eller tjenestefiler.
- Feil ved nødvendige tilstandskontroller.

Ikke bruk eksistensen av platform alene som tegn på gammel layout; platform er også en gyldig selvstendig komponent i den nye modellen.

Gi en tydelig melding om at den gamle layouten krever en separat migreringsprosedyre eller eksplisitt ny installasjon. La eksisterende state være urørt og fortsatt administrerbar med tidligere release.

Ikke lag tom identitetsdatabase eller nye signeringsnøkler som skjult erstatning for gammel state.

Dokumenter kompatibilitetsbruddet og før eventuell migrering som egen backlog-oppgave.

### 9. Avinstallasjon

Avhengigheter skal styre avinstallasjon:

- Identity kan ikke fjernes mens installerte apper krever den.
- Help skal ikke blokkere avinstallasjon av identity.
- Platform kan ikke fjernes mens identity, app1, app2 eller help krever den.

Når en app fjernes:

- Fjern dens route fra platform.
- Fjern dens offentlige OIDC-klientregistrering fra identity.
- Oppdater/restart bare de berørte tjenestene.
- Behold andre komponenters registreringer, tjenester og data.

Når identity fjernes uten dependenter:

- Fjern dens route fra platform.
- Behold platform og eventuell help.
- Behold identity-data som standard.

`--delete-data` skal bare slette valgt komponents egne data. Delt nettverk, felles CA og andre komponenters credentials skal ikke slettes.

### 10. Dev og bundling

Dev skal bruke samme komponentdeling og registreringsmodell som produksjon, selv om dev-helperen starter hele demosystemet samlet.

Oppdater image-bygging, image-utvalg og bundling etter behov.

Behold:

- Manifestdrevet image-utvalg.
- `imagePullPolicy: Never`.
- Ekskludering av privat state og bytecode.
- Checksums for alle leverte filer.
- Eksisterende fapolicyd- og SELinux-modell.

Identity-bundlen skal kunne transporteres og oppgraderes alene uten at platform- eller app-bundler må overføres på nytt.

Ikke endre immutable image-tags uten å bygge tilsvarende nye images.

### 11. Tester

Oppdater eksisterende tester uten å svekke sikkerhets- eller isolasjonskontroller. Legg til fokuserte tester for:

#### Installasjon og avhengigheter

- Platform kan installeres alene.
- Platform og help fungerer uten identity.
- Identity uten platform avvises før endringer.
- App uten identity avvises før endringer.
- Begge apprekkefølger fungerer etter platform og identity.
- Manglende og inkompatible avhengigheter gir tydelige feil.
- Oppgradering som bryter installerte dependenters versjonskrav avvises.

#### Registreringer og restart

- Bare route-endring påvirker platform.
- Bare klientendring påvirker identity.
- Begge endringer påvirker begge.
- Uendrede registreringer gir ingen unødvendig restart.
- Fjernede ruter/klienter er ikke aktive gjennom gamle importfiler.

#### Selvstendig identity-upgrade

Legg til et reelt acceptance-scenario som:

1. Installerer platform, identity og begge apper.
2. Oppretter brukerdata og verifiserer innlogging.
3. Bygger og overfører bare en nyere identity-bundle.
4. Installerer denne.
5. Verifiserer at ny identity-versjon og nytt image faktisk kjører.
6. Verifiserer innlogging og appenes databaseoperasjoner.
7. Verifiserer at identity-data og eksisterende credentials er beholdt.
8. Verifiserer at platform og appenes versjoner, tjenesteprosesser og konfigurasjon er uendret når registreringene ikke er endret.

Bruk en observerbar endring eller image-identitet som bevis; en oppdatert versjonsmarkør alene er ikke tilstrekkelig.

#### Avinstallasjon og gammel state

- Identity-avinstallasjon blokkeres av apper, men ikke help.
- Platform-avinstallasjon blokkeres av dependenter.
- Data beholdes som standard.
- Eksplisitt sletting er avgrenset til riktig komponent.
- Gammel samlet platform/identity-layout og blandet layout avvises uten endringer.

Behold relevant eksisterende dekning for help-only upgrade, app-only upgrade, offline installasjon, reboot og persistens. Tilpass forventningene til separate bundles.

### 12. Dokumentasjon

Oppdater README og relevant arkitektur-/testdokumentasjon slik at det er enkelt å forstå:

- Hva hver komponent eier.
- Hva hver bundle inneholder.
- Installasjonsrekkefølgen.
- Hvordan avhengigheter og versjonskrav kontrolleres.
- Hvem som konsumerer ruter og OIDC-klienter.
- Hvilke endringer som restarter hvilke tjenester.
- Hvordan identity oppgraderes alene.
- Hvilken state som er persistent.
- Hvorfor gammel samlet layout ikke oppgraderes automatisk.

Oppdater aktive kommandoeksempler og fjern foreldede antakelser om at app-bundler inneholder platform.

Ikke omskriv historiske verifikasjonsrapporter som om de ble kjørt med den nye arkitekturen.

### 13. Verifikasjon og leveranse

Kjør:

- Alle produkttester.
- Alle acceptance-harness-tester.
- Relevante ruff-, format-, pyright-, vermin- og shellcheck-kontroller.

Behold Python 3.6-kompatibilitet for host-verktøyene.

Kjør relevante faktiske acceptance-scenarioer i etablert labmiljø dersom dette er tilgjengelig og autorisert. Ikke reset eller endre andre miljøer.

Skill tydelig mellom lokale tester, harness-tester og målmaskinkjøringer. Hvis labkjøring ikke kan utføres, rapporter hvilke garantier som fortsatt er uverifisert.

Rapporter:

1. Ny komponent- og bundle-struktur.
2. Ressurser og state som har fått ny eier.
3. Avhengighets- og versjonsmodellen.
4. Restartreglene for ruter og klienter.
5. Konsekvensen for eksisterende installasjoner.
6. Testresultater og verifikasjonshull.
7. Utsatt arbeid, særlig migrering og modulrefaktorering.

Hold funksjonell oppdeling og senere modulrefaktorering adskilt. Foretrekk eksplisitte, enkle regler fremfor generelle abstraksjoner.


## 11. Plan an explicit retained core-to-platform migration

Status: superseded by the clarification in item 15: no existing installations
require migration. The original proposal below is retained as history, not
planned implementation work.

0.3.0 deliberately refuses retained or mixed core/platform state. Design and
review a separate procedure before migrating an important 0.2.x installation.
Inventory config, all credentials/certificates and CA, database and Data
Protection volumes, public registrations/imports, versions/dependencies,
Quadlet/systemd files and trust. Specify backups/restoration, volume identity/data
retention, explicit operator steps, verification and failure recovery. Preserve
password bytes and existing keys; never create an unnoticed empty replacement
database. Test against real historical releases and representative retained data.
Do not implement automatic rename, cleanup, resets or migration as part of item 1.
Include both retained core 0.2.x and combined platform/Identity 0.3.x sources.
Target the separate platform/Identity layout of 0.4.0; neither old layout is
automatically migrated. Coordinate backups, ownership and explicit transitions
with item 9 before implementing a procedure.

## 12. Rename component credential paths

Status: implemented in 0.4.1; fresh-install lab verification pending. See
[credential-path verification](acceptance/CREDENTIAL-PATHS.md). The deploy
refactor (item 1) is implemented; see its verification report.
This task uses fresh state only and requires no migration or backward compatibility.
The full agent message follows, with heading levels adjusted for this document.

Erstatt katalognavnet `generated-certificates/` med `credentials/` for komponentenes passord, sesjonsnøkler, private nøkler og sertifikater i `gunstein/podman_offline`.

Navnet `generated-certificates` beskriver innholdet feil: mappen inneholder også databasepassord og sesjonsnøkler, og materialet kan være både generert og eksternt levert.

Dette er en avgrenset opprydding av filstier. Ikke kombiner den med modulrefaktorering, passordrotasjon eller andre arkitekturendringer.

### 1. Ingen migrering eller bakoverkompatibilitet

Det finnes ingen eksisterende installasjoner som skal oppgraderes.

Implementer bare den nye layouten:

- Ikke lag migreringskode.
- Ikke lag fallback til `generated-certificates/`.
- Ikke legg til aliaser eller kompatibilitetsgrener.
- Ikke lag en flytteprosedyre for gammel state.
- Bruk fersk, isolert state i testene.

Sletting av andre eksisterende filer, credentials eller databasevolumer inngår ikke i oppgaven.

Historiske verifikasjonsrapporter og evidence skal beholdes uendret.

### 2. Undersøk gjeldende kode

Ta utgangspunkt i faktisk repo-status, inkludert eventuell gjennomført omdøping fra core til platform og utskilling av identity.

Kartlegg aktive referanser til `generated-certificates`, blant annet i:

- Komponentenes config-defaults.
- `GENERATED_SECRETS`, `SECRET_FILES` og `VOLUME_FILES`.
- Sertifikatscript og andre generatorer.
- OIDC-klientdescriptors og offentlig sertifikatregistrering.
- Database-preflight.
- Dev-script og smoke-tester.
- Acceptance-script og persistensobservasjoner.
- Bundle-beskyttelse mot private filer.
- README, PKI-dokumentasjon og eksempler.

### 3. Ny standardstruktur

Bruk `credentials/` under hver komponents state-mappe.

For app1 kan strukturen være:
```
/var/lib/myproduct/app1/
├── config.yaml
└── credentials/
    ├── database/
    │   └── password
    └── todo/
        ├── session-key
        ├── todo-client.key
        ├── todo-client.crt
        └── ca.crt
```

Dev bruker tilsvarende:
```
build/dev/app1/credentials/
```

Oppdater config, eksempelvis:
```
GENERATED_SECRETS:
- credentials/todo/session-key
- credentials/database/password

SECRET_FILES:
  app1-database-password:
  - credentials/database

VOLUME_FILES:
  app1-signing:
  - credentials/todo
```

Bruk samme prinsipp for øvrige komponenter.

Behold eksisterende undermapper og filnavn når de fortsatt er meningsfulle. Ikke utvid oppgaven til en generell reorganisering av credentials.

Felles PKI/CA-state utenfor komponentenes `generated-certificates/` skal ikke flyttes som en bieffekt.

### 4. Behold eksisterende funksjonalitet

Dette er en endring av host-side filstier. Behold:

- Secret-navn og keys.
- PVC-/volumnavn.
- Pod- og tjenestenavn.
- Containerens mount-paths, eksempelvis `/run/secrets/database/password` og `/certificates`.
- Databasebrukere og databasenavn.
- OIDC-klient-ID-er, scopes og offentlige URL-er.
- Runtime-mekanismen for connection strings.
- Config-precedence og autoritativ persistent produksjonsconfig.

Oppdater alle host-side referanser, også sertifikatstier i `client.yaml` eller tilsvarende descriptors.

Unngå endringer i applikasjonskode og images når containergrensesnittet er uendret.

### 5. Behold genererings- og sikkerhetsreglene

Databasepassord og sesjonsnøkler skal fortsatt genereres gjennom eksisterende `GENERATED_SECRETS`.

Sertifikatscriptet skal skrive sitt materiale til de nye stiene. Ikke flytt databasepassordgenerering tilbake til sertifikatscriptet.

Behold eksisterende garantier:

- Manglende hemmeligheter opprettes bare når dette er tillatt.
- Eksisterende gyldige filer beholdes byte-for-byte ved restart/redeploy.
- Tomme eller ugyldige filer gir feil.
- Manglende databasepassord med eksisterende databasevolum avvises.
- Private fil- og katalogrettigheter beholdes.
- Symlink-escape og utrygge output-stier avvises.
- Credentials og komplette connection strings eksponeres ikke i logger.

Disse kontrollene gjelder vanlig drift av den nye layouten. Det skal ikke innføres egne kontroller eller fallback-regler for gammel layout.

### 6. Dev, bundling og acceptance

Oppdater alle helper-script som leser, genererer, overfører eller sammenligner credentials.

Nye dev- og produksjonsinstallasjoner skal bruke samme layout under sine respektive komponentmapper.

Bundle-beskyttelsen skal fortsatt hindre at credentials følger med offline-arkivene, inkludert kopiering gjennom symlink-aliaser.

Behold kontrollene som følger deklarerte secret-filer. Ikke erstatt dem med bare et enkelt navnefilter for mappen `credentials`.

Behold checksum-garantier, offline-egenskaper og eksisterende SELinux-/fapolicyd-kontroller.

### 7. Tester

Oppdater eksisterende tester og legg bare til fokuserte regresjoner der dekning mangler.

Verifiser:

- Defaults og config-initialisering bruker `credentials/`.
- Genererte filer havner på riktige stier i dev og produksjon.
- Sertifikatscriptet bruker de nye stiene.
- OIDC-klientregistrering finner riktig offentlig sertifikat.
- Server og klient fortsatt bruker samme databasepassord.
- Restart/redeploy beholder credentials byte-for-byte.
- Database-preflight fortsatt avviser manglende passord når volumet finnes.
- Secret-/PVC-navn og container-mounts er uendret.
- Private filer og symlink-aliaser ikke havner i bundles.
- Smoke- og acceptance-script bruker de nye plasseringene.

Ikke legg til migreringstester eller tester som krever støtte for gamle configstier.

### 8. Dokumentasjon og opprydding

Dokumenter rollene tydelig:

- `credentials/` inneholder passord, nøkler og sertifikater.
- `GENERATED_SECRETS` angir hvilke filer som genereres.
- `SECRET_FILES` og `VOLUME_FILES` angir hvordan filene leveres til containerne.

Søk gjennom hele repoet etter `generated-certificates`. Oppdater aktive referanser i kode, config, tester, eksempler og operatørdokumentasjon.

Behold historiske rapporter og eventuelle fixtures som eksplisitt representerer en historisk release. Forklar gjenværende forekomster i sluttrapporten.

Ikke marker tidligere labresultater som verifikasjon av denne endringen.

### 9. Verifikasjon og leveranse

Kjør:

- Alle produkttester.
- Alle acceptance-harness-tester.
- Relevante ruff-, format-, pyright-, vermin- og shellcheck-kontroller med prosjektets eksisterende oppsett.

Behold Python 3.6-kompatibilitet for host-verktøyene.

Kjør relevante ferske installasjons-/e2e-scenarioer i etablert labmiljø dersom dette er tilgjengelig og autorisert. Ikke reset andre miljøer.

Skill tydelig mellom lokale tester, harness-tester og faktisk container-/målmaskinverifikasjon. Oppgi hva som ikke kunne kjøres.

Rapporter kort:

1. Hvilke stier og filer som er endret.
2. Eventuelle bevisst beholdte historiske referanser.
3. Testresultater og verifikasjonshull.
4. Bekreftelse på at det ikke er innført migreringskode eller fallback til gammel layout.

Foretrekk en enkel, konsekvent navneendring fremfor nye abstraksjoner.

## 13. Retry-safe install and uninstall

Status: implemented in 0.4.2; local failure-injection verification passed, real
Podman/systemd behavior remains unverified here. See [retry verification](acceptance/RETRY-SAFETY.md).
This is a bounded correctness fix for retrying failed operations, not a transaction
framework or module refactor. The full agent message follows, with Markdown
formatting adjusted for this document.

Implementer trygg gjentakelse etter feil i installasjon og avinstallasjon i gunstein/podman_offline.

Oppgaven gjelder to konkrete feil i deploy.py:

1. Et nytt installasjonsforsøk kan hoppe over nødvendige omstarter av Identity/platform etter et mislykket forsøk.
2. En avinstallasjon kan bli stående halvferdig, samtidig som neste forsøk avvises fordi installasjonsmarkøren allerede er slettet.

Dette er en avgrenset feilretting. Ikke gjennomfør den planlagte modulrefaktoreringen, endre komponentarkitekturen eller innfør et generelt transaksjonsrammeverk.

### 1. Les og forstå eksisterende flyt

Les først:

- install_components()
- install_component_plan()
- write_registrations()
- registration_stage()
- component_imports()
- uninstall()
- relevante tester for installasjonsfeil, komponenter og Identity

Funksjonsnavnene kan ha endret seg. Finn tilsvarende kode i gjeldende branch.

Komponentmodellen er:

- platform eier proxy og ruteregistreringer.
- identity eier IdentityServer og klientregistreringer.
- app1 og app2 avhenger av platform og identity.
- help avhenger av platform.

Ruteregistreringer og klientregistreringer skal fortsatt behandles separat. En route-endring skal normalt påvirke platform, mens en klientendring skal påvirke identity.

### 2. Feilen ved installasjon

Dagens flyt skriver registreringer før alle nødvendige tjenester er restartet.

Et eksempel:

1. App1 har en ny route og klientregistrering.
2. Installer skriver begge registreringene til persistent state.
3. Restart av app1 feiler.
4. Installer avslutter før Identity og platform er restartet.
5. Operatøren kjører samme installasjon på nytt.
6. Registreringsfilene har allerede riktig innhold og regnes som uendret.
7. Identity og platform blir derfor ikke restartet.

Det andre forsøket kan rapportere suksess selv om de kjørende tjenestene ikke har tatt i bruk registreringene.

En tilsvarende feil kan oppstå dersom skriving av importarkiver eller restart av en av registreringseierne feiler.

Krav: Et nytt installasjonsforsøk må fullføre nødvendig arbeid fra forrige forsøk. Det er ikke tilstrekkelig å sammenligne nye registreringer med filene som allerede ligger på disk.

### 3. Løsning for installasjon

Velg en enkel, eksplisitt mekanisme for å huske ufullført arbeid mellom prosesskjøringer.

En liten persistent pending-fil er et mulig valg. Den kan for eksempel angi at registreringene til identity og/eller platform ennå ikke er bekreftet tatt i bruk.

Det konkrete filnavnet og formatet kan tilpasses eksisterende kode. Følg disse reglene:

- Registrer nødvendig arbeid før endringer som ellers kan gjøre at behovet blir glemt.
- Pending-state skal overleve at installer avslutter eller prosessen avbrytes.
- Ved neste forsøk skal pending-state leses og kombineres med eventuelle nye endringer.
- Nødvendige importarkiver må skrives på nytt dersom forrige forsøk ikke fullførte dette.
- Berørte tjenester må restartes og kontrolleres med eksisterende suksesskriterier.
- Fjern bare pending-state for arbeid som faktisk er fullført.
- Hvis en restart eller kontroll feiler, skal ufullført arbeid fortsatt være registrert.
- Et nytt forsøk med identiske registreringsfiler må fortsatt utføre pending arbeid.

Pending-state skal inneholde bare nødvendig metadata, aldri passord, private nøkler eller komplette konfigurasjoner.

Bruk eksisterende mønstre for private filrettigheter og trygg filskriving. Ikke følg symlinker til vilkårlige steder. Ugyldig pending-state skal gi en tydelig feil, ikke ignoreres.

Ikke løs problemet ved å restarte alle tjenester på hver installasjon.

Bevar normal oppførsel:

- Uendrede registreringer uten pending arbeid skal ikke restarte Identity/platform.
- Bare route-endring skal normalt restarte platform.
- Bare klientendring skal normalt restarte identity.
- Begge endringer skal restarte begge.
- Sibling-applikasjoner skal ikke restartes som en bivirkning.

Hvis du velger en annen løsning enn pending-state, må den dekke de samme feiltilfellene og forklares tydelig.

### 4. Feilen ved avinstallasjon

Dagens avinstallasjon sletter blant annet installasjonsmarkøren før hele operasjonen er fullført.

Et eksempel:

1. App1 stoppes.
2. Quadlet/YAML og registreringer slettes.
3. Installasjonsmarkøren slettes.
4. Restart av Identity eller platform feiler.
5. Operatøren kjører uninstall på nytt.
6. Installer avviser forsøket fordi app1 ikke lenger regnes som installert.

Med --delete-data kan også volumfjerning feile etter at installasjonsmarkøren er borte.

Krav: Operatøren skal kunne gjenta avinstallasjonen og fullføre den uten manuell rekonstruksjon av markører, YAML eller registreringer.

### 5. Løsning for avinstallasjon

Gjør avinstallasjonen mulig å fortsette etter delvis gjennomføring.

Ikke løs dette bare ved å flytte sletting av installasjonsmarkøren til slutten. Tidligere slettet YAML eller andre filer kan fortsatt være nødvendige for å vite hva som gjenstår.

Før destruktive steg må nødvendig informasjon være validert og bevart slik at neste kjøring vet:

- hvilken komponent som avinstalleres
- om operasjonen inkluderer --delete-data
- hvilke tjenester som skal stoppes eller oppdateres
- hvilke registreringseiere som må oppdateres
- hvilke konkrete volumer som eventuelt skal slettes

Bruk en liten, eksplisitt tilstand for pågående avinstallasjon dersom det er nødvendig. Ikke lag en generell operasjonsmotor.

Følg disse kravene:

- Avhengighetskontroller skal fortsatt kjøres før avinstallasjonen starter.
- En komponent med pågående avinstallasjon må ikke behandles som en frisk, tilgjengelig avhengighet for nye installasjoner.
- Gjentatt sletting av filer som allerede er fjernet av samme operasjon skal være trygg.
- Manglende volum ved retry kan regnes som allerede slettet.
- Feil ved kontroll av et volum skal fortsatt være en feil; det må ikke tolkes som at volumet mangler.
- Volumlisten skal komme fra validert, komponentavgrenset informasjon.
- Ikke utvid sletting til andre komponenters volumer eller state.
- Oppdatering av registreringer og nødvendige omstarter må kunne gjentas.
- Marker operasjonen som fullført først når alle nødvendige steg har lykkes.
- Rydd opp i pending-state etter fullført operasjon.

Bevar forskjellen mellom:

- uninstall: behold data, config og credentials.
- uninstall --delete-data: slett bare den valgte komponentens relevante data og state.

Et retry må ikke utilsiktet endre en avinstallasjon uten datasletting til en avinstallasjon med datasletting. Definer og dokumenter hvordan avvikende flagg håndteres. Den enkleste løsningen er å kreve samme valg som da operasjonen startet og gi en tydelig feil ved avvik.

### 6. Samspill mellom installasjon og avinstallasjon

Definer enkel og tydelig oppførsel dersom en ny kommando møter en ufullført operasjon.

For eksempel:

- install må ikke ignorere en pågående avinstallasjon av samme komponent.
- uninstall må ikke slette eller overse pending registreringsarbeid på en måte som etterlater feil runtime-state.
- En operasjon må ikke fjerne pending arbeid som tilhører en annen operasjon.

Det er akseptabelt å avvise en konflikt med en tydelig melding om hvilken kommando operatøren må kjøre for å fullføre først.

Ikke innfør automatisk rollback eller automatiske reparasjoner av ukjent state.

### 7. Tester for installasjon

Bruk eksisterende testoppsett og feilinjeksjon. Legg minst til følgende scenarioer:

#### A. App-restart feiler etter registreringsskriving

1. Installer en app med endret route og klientregistrering.
2. La app-restart feile etter at registreringene er skrevet.
3. Verifiser at installasjonen feiler.
4. Kjør samme installasjon igjen uten feilen.
5. Verifiser at nødvendige importarkiver oppdateres og både Identity og platform restartes.
6. Verifiser at pending-state fjernes etter suksess.

#### B. En registreringseier feiler

1. La restart eller etterfølgende kontroll av Identity/platform feile.
2. Kjør installasjonen igjen.
3. Verifiser at ufullført arbeid utføres, selv om registreringsfilene er identiske.

#### C. Importarkivskriving feiler

1. La skriving av et nødvendig importarkiv feile etter at registreringer er skrevet.
2. Kjør installasjonen igjen.
3. Verifiser at importarkivet faktisk oppdateres før operasjonen regnes som fullført.

#### D. Normal installasjon er fortsatt avgrenset

Verifiser fortsatt de fire kombinasjonene:

- ingen registreringsendring
- bare route-endring
- bare klientendring
- begge endringer

Uten pending arbeid skal ingen ekstra fellestjenester restartes.

### 8. Tester for avinstallasjon

Legg minst til følgende scenarioer:

#### A. Restart av registreringseier feiler

1. Start avinstallasjon av en installert app.
2. La restart av Identity eller platform feile.
3. Kjør avinstallasjonen igjen.
4. Verifiser at den fullføres selv om noen filer allerede er slettet.
5. Verifiser at registreringene er fjernet fra de oppdaterte importarkivene.
6. Verifiser at pending-state ryddes opp.

#### B. Volumsletting feiler

1. Start uninstall --delete-data med flere komponentvolumer.
2. La sletting av et senere volum feile etter at et tidligere volum er fjernet.
3. Kjør samme kommando igjen.
4. Verifiser at allerede slettede volumer håndteres og resterende arbeid fullføres.
5. Verifiser at andre komponenters state er uendret.

#### C. Avinstallasjon uten datasletting

Et mislykket forsøk og retry skal bevare bytes i config og credentials samt databasevolumer.

#### D. Konflikter og ugyldig state

Test:

- retry med avvikende valg for --delete-data
- installasjon mens samme komponent har pågående avinstallasjon
- ny installasjon som krever en komponent med pågående avinstallasjon
- ugyldig eller symlinket pending-state

Retry-testene må representere en ny prosesskjøring: løsningen skal ikke være avhengig av variabler fra første forsøk. Bruk samme persistente testkatalog, men nullstill midlertidig tilstand mellom forsøkene.

### 9. Avgrensning og kompatibilitet

Bevar:

- eksisterende rotkommandoer
- Python 3.6-kompatibilitet for deploy-koden
- bundle-avhengigheter og versjonsregler
- checksums og offline installasjon
- eksisterende secret-generering og credential-stier
- SELinux- og fapolicyd-kontroller
- komponentisolasjon og persistente data

Ikke:

- flytt deploy til en Python-pakke som del av denne oppgaven
- legg til passordrotasjon
- regenerer credentials ved retry
- innfør ny migreringslogikk
- endre normale tjenesteomstarter utover det feilrettingen krever
- legg pending-state i release-katalogen eller offline-bundlen

### 10. Dokumentasjon, sjekker og rapport

Dokumenter kort hvordan operatøren gjentar en mislykket installasjon eller avinstallasjon, og hvordan eventuelle konflikter rapporteres.

Kjør:

- produkttestene
- acceptance-harness-testene
- ruff
- formatkontroll
- pyright
- vermin
- shellcheck

Legg bare til nye reelle acceptance-scenarioer dersom de gir nødvendig dekning utover målrettede feilinjeksjonstester. Ikke påstå at stubbet testing beviser faktisk Podman/systemd-oppførsel.

Rapporter:

1. Årsaken til de to feilene.
2. Hvordan ufullført arbeid lagres og fullføres ved retry.
3. Hvilke filer som er endret.
4. Hvilke nye feilscenarioer testene dekker.
5. Faktiske testresultater og sjekker som ikke kunne kjøres.
6. Eventuelle begrensninger.

Foretrekk små, tydelige funksjoner og eksplisitte steg. Målet er at en middels erfaren Python-utvikler enkelt skal kunne forstå hvorfor et nytt forsøk er trygt.

## 14. Tighten app credential delivery and remove unused API secret

Status: implemented in 0.4.4; local checks and real target verification are
reported in [credential delivery](acceptance/CREDENTIAL-DELIVERY.md). Target
verification remains pending. The original agent message follows.

Rett credential-håndteringen i `gunstein/podman_offline` med en liten, målrettet endring.
Behold dagens komponentarkitektur og offline installasjonsmodell.

### 1. Bakgrunn og bekreftede observasjoner

App1 og app2 deklarerer `credentials/todo/session-key` i `GENERATED_SECRETS`.
Hele `credentials/todo/`, inkludert session key og privat klientnøkkel, leveres i dag
gjennom `VOLUME_FILES` til appens signing-PVC og monteres skrivebeskyttet på
`/certificates` i backend. Frontend får ikke denne mounten.

`deployment/render.py: generate_secrets()` oppretter originalfilen med modus `0600`.
`write_file_archives()` oppretter selve arkivet med `0600`, men `normalize()` setter
vanlige filer inne i arkivet til `0644`. Dette er lokalt reprodusert med en syntetisk
session key. Faktiske rettigheter etter Podman-import er ikke verifisert her.
PVC-bruk alene er ikke et bekreftet sikkerhetshull; vurder tilgang og livssyklus,
ikke bare navnet på YAML-ressursen.

Identity deklarerer også `credentials/app/ApiResources__0__ApiSecrets__0__Value` og
leverer den via `identity-api-secrets` og `envFrom`. Gjennomgangen fant ingen bruk
av verdien i dagens Identity-kode. Bekreft dette før den fjernes.

### 2. Kartlegg før endring

Les `AGENTS.md` dersom den finnes, README, ARCHITECTURE og relevante tester.
Følg de faktiske filene gjennom:

- `components/app1/config.defaults.yaml` og tilsvarende for app2/identity.
- Komponentenes manifester og `scripts/generate-certificates.sh`.
- `deployment/render.py`: generering, filgrupper, Secret/PVC og importarkiver.
- `deployment/deploy.py`: installasjon, retry og avinstallasjon.
- `apps/todo-backend/app.py` og `apps/identity/Program.cs`.

Session key brukes som Flask `SECRET_KEY` til sesjonscookies. Den private
klientnøkkelen brukes til `private_key_jwt` mot Identity. Dette er forskjellige
hemmeligheter med forskjellige oppgaver; ingen av dem skal leveres til frontend.

### 3. Stram inn levering og rettigheter

Foretrekk å levere session key og privat klientnøkkel gjennom eksisterende
`SECRET_FILES`, som for databasepassord og Identitys signeringsnøkkel. Avklar at
valgt løsning støttes av målversjonen av Podman og eksisterende `.kube`-flyt.
En liten credential-gruppe per app er tilstrekkelig; ikke innfør et nytt rammeverk.

- Behold persistente originalfiler og samme bytes gjennom normale oppgraderinger,
  gjentatt installasjon og retry. Ikke regenerer eller roter nøkler ved flyttingen.
- Sørg for eksplisitte restriktive rettigheter for hemmelige filer i containeren,
  for eksempel `0400` eller `0600`, med eierskap som passer prosessen som leser dem.
  Verifiser at Podman faktisk anvender feltene; ikke anta Kubernetes-oppførsel.
- Behold skrivebeskyttet mount og tilgang bare i backend. Behold eksisterende
  filstier i containeren hvis dette gir den enkleste og tydeligste løsningen.
- Offentlige sertifikater kan følge samme beskyttede gruppe når det forenkler
  mounten; ikke skap ekstra abstraksjoner bare for å skille offentlige filer.
- Session key og privat klientnøkkel skal ikke samtidig bli liggende i et aktivt
  generert `VOLUME_FILES`-arkiv etter endringen.
- Ikke sett alle generelle importfiler til `0600` uten å vurdere offentlige
  payloads, katalogtilgang og containernes UID/GID. Dersom hemmeligheter fortsatt
  må leveres gjennom importarkiv, begrunn valget og bevar restriktive rettigheter.
- Bevar avinstallasjonens skille mellom å beholde state og eksplisitt
  `--delete-data`. Sletting skal fortsatt være avgrenset til valgt komponent.

En Secret gir ikke automatisk kryptering eller minnebasert lagring i Podman.
Renderet YAML med base64-kodede secrets er sensitiv. Beskytt YAML, originalfiler,
eventuelle arkiver og runtime-kopier, og unngå verdier i logger og testutskrifter.

### 4. Fjern ubrukt API-secret

Hvis kartleggingen bekrefter at API-secret-en er ubrukt, fjern dens generering,
Secret-deklarasjon, `envFrom`-referanse og eventuelle unødvendige katalogopprettelser.
Oppdater relevante tester og dokumentasjon. Ikke fjern legitime API-scopes,
klientsertifikatautentisering, databasepassord eller Identitys tokensignering.
Ingen automatisk sletting av ukjente eksisterende credential-filer.

### 5. Tester og dokumentasjon

Legg til målrettede tester som verifiserer:

- Riktig leveringsmåte, mount, eierskap/rettighetsinnstillinger og uendrede
  credential-bytes. Undersøk faktisk generert YAML og eventuelle arkivmedlemmer.
- Separate nøkler for app1 og app2 og ingen credential-mount i frontend.
- Ingen duplisert privat nøkkel/session key i appens genererte importarkiv.
- Installasjon, upgrade og retry beholder nøklene, samt fortsatt trygg og avgrenset
  avinstallasjon med og uten datasletting.
- Ubrukt API-secret genereres eller refereres ikke lenger.
- Private filer og bytecode følger fortsatt ikke med i offline-bundles.

Oppdater README og relevant test-/arkitekturdokumentasjon med faktisk filflyt og
skillet mellom en hemmelig verdi og YAML-typen `Secret`. Brukerens diagramskisser
er foreløpig til diskusjon; ikke legg dem inn uten egen avtale.

Kjør repoets dokumenterte produkttester, acceptance-harness-tester, ruff,
formatkontroll, pyright, vermin og shellcheck. Behold Python 3.6-kompatibilitet
for host-verktøyene. Oppdater berørte image-/releaseversjoner etter repoets
konvensjoner dersom endringen krever nye images; ikke gjenbruk en uforanderlig tag.

Beskriv eller utvid målrettet labverifikasjon av reelle filmoduser, lesetilgang,
innlogging, sesjoner etter restart/upgrade, klientautentisering og avinstallasjon.
Ikke start destruktive VM-/snapshot-kjøringer uten eksplisitt autorisasjon.
Skill mellom lokale tester, statisk vurdering og faktisk Podman-verifikasjon.

### 6. Avgrensning og leveranse

Ingen eksisterende installasjoner trenger migrering fra gamle layouts. Ikke bygg
migreringskode, fallback, automatisk nøkkelrotasjon eller en ny secret manager.
Normale oppgraderinger i den støttede modellen skal fortsatt bevare private filer
og data. Ikke redesign Flask-/OIDC-autentiseringen eller tilpass demoen til en
hypotetisk C#/GraphQL-applikasjon som del av denne oppgaven.

Rapporter valgt løsning, konkrete endringer, testresultater og hva som gjenstår i
lab. Forklar hvilke sikkerhetsegenskaper som faktisk er forbedret, uten å påstå at
et bytte fra PVC til Secret alene gir kryptering eller en ny isolasjonsgrense.

## 15. Remove obsolete legacy layout refusal checks

Status: implemented in 0.4.5; local checks and remaining target verification are
reported in [layout cleanup](acceptance/LEGACY-CHECK-CLEANUP.md). The original
agent message follows. No existing installations require migration.

Melding til agenten:

Fjern kontrollene som bare oppdager og avviser historisk core-layout eller
kombinert platform/Identity-layout i `gunstein/podman_offline`.
`core-identity-data` i `deployment/deploy.py` er ett konkret eksempel; dagens
Identity-volum heter `identity-data`. Det gamle navnet brukes til avvisning,
ikke som et aktivt databasevolum.

- Kartlegg `reject_legacy_layout()`, `reject_combined_platform()`,
  `legacy_volume_exists()` og tilsvarende kontroller i sertifikat-/dev-script,
  tester og aktive acceptance-scenarioer. Ta utgangspunkt i siste repo-status.
- Fjern avvisningskontrollene, tilhørende kall og feiltekster om separate
  migreringsprosedyrer. Ikke bare erstatt gamle volumnavn med nye navn i disse
  kontrollene; dagens volumer skal ikke avvises som historisk state.
- Oppdater tester og aktiv operatørdokumentasjon slik at de beskriver dagens
  støttede layout. Behold historiske rapporter, evidence og fixtures som
  eksplisitt representerer gamle releaser; forklar gjenværende gamle navn.
- Ikke innfør migrering, fallback, aliaser, kompatibilitetsgrener, automatisk
  opprydding eller sletting/flytting av gamle filer eller volumer. Oppgavene 4
  og 11 skal ikke implementeres; de er historiske forslag som er erstattet av
  presiseringen om at ingen eksisterende installasjoner trenger migrering.
- Behold normal oppgradering og retry i dagens komponentmodell: config,
  credentials og data skal fortsatt bevares. Behold database-preflight,
  avhengighets-/versjonskontroller, pending-state-validering, komponentisolasjon,
  sikre filstier/rettigheter og bundle-beskyttelse.

Kjør produkttester, acceptance-harness-tester og repoets relevante ruff-, format-,
pyright-, vermin- og shellcheck-kontroller samt `git diff --check`. Behold Python
3.6-kompatibilitet for host-verktøyene. Rapporter hva som er fjernet, hvilke
historiske referanser som er beholdt, testresultater og eventuelle labhull.

## 16. Combine secret generation and file delivery declarations

Status: implemented in 0.4.6 after item 14; source-level generate is supported
for both delivery groups. See [file sources](acceptance/FILE-SOURCES.md) for
verification and remaining lab work. The original agent message follows.

Melding til agenten:

Forenkle config-modellen i `gunstein/podman_offline` slik at eventuell generering
deklareres sammen med filene som leveres gjennom `SECRET_FILES` eller
`VOLUME_FILES`. Fjern behovet for en separat `GENERATED_SECRETS`-liste og dobbelt
vedlikehold av samme filsti. Målet er at en middels erfaren utvikler enkelt skal
forstå både hvor en fil kommer fra og hvordan den leveres til containeren.

Et mulig format, som et utgangspunkt for vurdering, er:

```yaml
SECRET_FILES:
  app2-database-password:
    directory: credentials/database
    generate:
    - password
  identity-signing:
    directory: credentials/identity
```

Her er `generate` relativt til den deklarerte katalogen og angir bare filer som
skal opprettes hvis de mangler. Uten `generate` brukes eksisterende filer.
Støtt samme prinsipp for `VOLUME_FILES`, siden genererte sesjonsnøkler i dagens
modell leveres gjennom volumer. Undersøk om formatet bør bruke en liste med
filkilder fremfor én `directory`, slik at nødvendig støtte for flere kildefiler
og kataloger ikke forsvinner. Velg én enkel og konsekvent modell; ikke innfør et
generelt generator-/pluginrammeverk eller to parallelle config-formater.

- Les gjeldende defaults, config-validering, generering, rendering, database-
  preflight, bundling, dev-/sertifikatscript og tester før formatet bestemmes.
- Behold dagens genereringsregler og tidspunkt: bare eksplisitt deklarerte
  manglende filer opprettes der dette er tillatt. Eksisterende gyldige filer
  beholdes byte-for-byte; tomme/ugyldige filer gir feil. Manglende databasepassord
  med eksisterende databasevolum skal fortsatt avvises før generering.
- Sertifikater og private signeringsnøkler skal fortsatt forberedes separat.
  Den nye deklarasjonen skal ikke gjøre deploy til en sertifikatutsteder.
- Behold credential-stier, Secret-navn og keys, volum-/PVC-navn, container-mounts,
  passordformat/-lengde, config-precedence og autoritativ persistent config.
  Behold sikre filstier, symlink-kontroller og private fil-/katalogrettigheter.
- Bundle-beskyttelsen må fortsatt følge deklarerte private filer, inkludert
  symlink-aliaser, og ikke bare filtrere på katalog- eller filnavn. Credentials
  og komplette connection strings skal ikke eksponeres i logger eller bundles.
- Oppdater alle aktive configs, eksempler, hjelpere, tester og dokumentasjon til
  den nye deklarasjonen. Behold historiske rapporter og eksplisitte historiske
  release-fixtures. Ingen eksisterende installasjoner trenger config-migrering:
  ikke lag migreringskode, fallback, aliaser eller støtte for gammelt format.

Legg til målrettet dekning av genererte og eksternt leverte filer, begge
leveringsmåter, ugyldige deklarasjoner/stier, config-initialisering, database-
preflight, byte-bevaring ved restart/redeploy/retry og bundle-beskyttelse.
Behold config, credentials og data ved normale oppgraderinger i den nye modellen.
Ikke kombiner med passordrotasjon, endret komponentarkitektur eller bred
modulrefaktorering.

Kjør produkttester, acceptance-harness-tester og relevante ruff-, format-,
pyright-, vermin- og shellcheck-kontroller samt `git diff --check`. Behold Python
3.6-kompatibilitet for host-verktøyene. Rapporter valgt format, endrede filer,
testresultater og hva som eventuelt gjenstår å verifisere i lab.

## 17. Use an init container for database preparation in one demo app

Status: implemented in 0.4.8. App1 uses a real schema-preparation init container;
app2 retains backend initialization. Local checks and remaining real target
verification are documented in [app1 init verification](acceptance/APP1-INIT.md).
The original agent message follows.

Melding til agenten:

La én av appene i `gunstein/podman_offline` bruke `initContainers` til reell
databaseklargjøring før backend starter. Velg og begrunn en egnet app ut fra
gjeldende kode og manifests, fortrinnsvis app1 eller app2. Dagens Todo-backend
oppretter tabellen i oppstartskoden, mens Identity klargjør brukertabellen selv.
Flytt et konkret, nødvendig klargjøringssteg til init-containeren; ikke legg til
en symbolsk init-container som bare kjører `echo` eller en ventekommando.

- Undersøk Podman/Quadlet-oppstarten og hvor PostgreSQL kjører før løsningen
  velges. En init-container må ikke vente på en ordinær databasecontainer i
  samme pod som først starter etter init-containeren. Dokumenter hvordan
  databasen faktisk blir tilgjengelig før klargjøringssteget kjører.
- Backend skal starte først etter vellykket init. Databaseventing skal være
  tidsbegrenset, og init-feil skal gi en tydelig feil uten å eksponere passord
  eller komplette connection strings. Bruk appens eksisterende credential-
  mekanisme og samme databasepassord som databasen og backend.
- Klargjøringen skal være idempotent: fersk installasjon oppretter nødvendig
  skjema; restart, redeploy og retry bevarer eksisterende databaseinnhold og
  credentials. Ikke innfør passordrotasjon, destruktive resets, migrering fra
  historiske layouts eller et generelt database-migreringsrammeverk.
- Behold den andre appens virkemåte. Appene deler backend-kilde/image i dagens
  modell; unngå utilsiktet å kreve init-klargjøring også i appen som ikke endres.
  Behold isolasjon fra platform, identity og sibling-appens data og tjenester.
- Oppdater nødvendig appkode, manifests, dev-flyt, bundling, tester og README.
  Offline-bundlen skal inneholde alle nødvendige images; ingen nedlasting av
  kode eller pakker ved init. Følg repoets regler for nye image-/releaseversjoner.

Legg til målrettede tester for oppstartsrekkefølge, init-feil, tidsavbrudd og
gjentatt klargjøring uten datatap. Kjør produkttester, acceptance-harness-tester
og relevante lint-, format-, type-, kompatibilitets- og shellkontroller samt
`git diff --check`. Behold Python 3.6-kompatibilitet for host-verktøyene.
Beskriv nødvendig labverifikasjon av faktisk Podman-oppførsel, inkludert fersk
installasjon og restart med beholdte data. Ikke påstå at stubbede tester beviser
reell init-container-rekkefølge. Rapporter valgt app, konkret flyt, endrede filer,
testresultater og verifikasjonshull.

## 18. Move proxy configuration out of apps and use stock nginx from YAML

Status: implemented in 0.4.7 with the revised scope: existing app image building
is unchanged, standard nginx is configured through platform YAML. See
[proxy verification](acceptance/NGINX-YAML.md) for checks and remaining lab work.
The original revised agent message follows.

Melding til agenten:

Fjern den egendefinerte proxyen fra `apps/` i `gunstein/podman_offline`. Platform
skal referere et versjonert standard nginx-image direkte, og alt som trengs for
proxyens konfigurasjon/oppstart skal deklareres i manifest-YAML under platform.
Det skal ikke lenger bygges et eget proxy-image.

Image-byggingen for de øvrige appene skal være som i dag. Ikke flytt byggelogikk
til Python og ikke refaktorer `dev/build-images.sh`, `dev/pull-images.sh` eller
bundle-verktøyet som del av denne oppgaven. Behold eksisterende
komponentarkitektur, CLI og offline installasjonsmodell.

### 1. Les eksisterende flyt

Les `AGENTS.md` dersom den finnes, README, ARCHITECTURE, BACKLOG og relevante
tester. Undersøk minst `dev/build-images.sh`, `dev/pull-images.sh`,
`bundle.py: manifest_images()` / image-validering / arkivering,
`apps/*/Containerfile`, `apps/proxy/default.conf`, `15-resolver.envsh`,
platform-manifestene, ruteregistreringene og image-/registry-acceptance-hjelperne.
Funksjonsnavn og filer kan ha endret seg; bruk faktisk gjeldende repo-status.

### 2. Behold eksisterende image-bygging

- Behold `dev/build-images.sh` og dagens oppskrifter/build contexts/tags for
  øvrige app-images. Ikke lag en ny Python-fil eller wrapper for image-bygging.
- Behold manifestdrevet image-discovery, skille mellom lokale demo-builds og
  registry-pull, PostgreSQLs gjeldende upstream-pull/lokale tag, feilkoder og
  validering. Ikke legg til fallback-bygging ved pull-feil.
- Det eneste tilsiktede utslaget i image-flyten er at proxyen blir et vanlig
  registry-image: den hentes av eksisterende pull-flyt og bygges ikke lokalt.
  Tilpass bare hjelpere som konkret avhenger av det gamle proxy-imaget.

### 3. Proxy uten eget image-bygg

- Erstatt `localhost/myproduct-proxy:...` med et fullt kvalifisert, eksplisitt
  versjonert standard nginx-image i platform-manifestet. Ikke bruk `latest`.
  Undersøk dagens baseimage og unngå en unødvendig nginx-versjonsendring.
- Flytt nødvendig nginx-konfigurasjon, template og eventuell liten oppstartskode
  inn i YAML, for eksempel ConfigMap-data og eksplisitt command/args eller det
  valgte imagets støttede entrypoint-mekanisme. Det skal ikke kreves et nytt
  image, proxy-Containerfile eller separate proxy-konfigurasjons-/scriptfiler i
  `apps/proxy/`. Fjern disse når aktive avhengigheter er erstattet.
- Behold runtime DNS fra containerens `/etc/resolv.conf` og dynamisk oppslag av
  komponentnavn. Platform må kunne starte uten appene/Identity, og routes skal
  fungere når tjenester kommer til eller restartes med nye adresser.
- Behold HTTPS_PORT, TLS-filer, begrensninger, `/livez`, ukjent-route 404 og
  `/routes/installed.conf`. Ikke hardkod app-/Identity-ruter i proxyens grunnconfig.
  Behold TLS-mount, rutemount, readOnly, hostname, hostIP/port og healthcheck.
- Respekter rendererens eksisterende hele-verdi-`@@...@@`-kontrakt. Hvis nginx-
  templating skjer ved containeroppstart, begrens variabelsubstitusjon slik at
  nginx-variabler i konfigurasjon/ruter ikke utilsiktet erstattes. Ikke innfør en
  generell endring av deploy-rendereren for å løse proxy-templating.
- Verifiser nødvendig shell/verktøystøtte, ConfigMap-mounts, filmoduser og
  oppstartsrekkefølge for faktisk valgt image og Podman-versjon. Ikke skriv til
  skrivebeskyttede mounts; kjør nginx som hovedprosess med korrekt signalhåndtering.

### 4. Offline, tester og dokumentasjon

Det nye nginx-imaget skal oppdages fra manifestet, hentes på byggemaskinen via
pull-flyten, arkiveres med platform-bundlen og lastes/verifiseres før installasjon.
Behold `imagePullPolicy: Never` på målmaskinen, checksums, image-navnvalidering og
isolasjon mellom bundles. Produksjon skal ikke hente images eller pakker fra nett.
Oppdater dev-/acceptance-hjelpere som fortsatt forventer egen proxy-build eller
filene under `apps/proxy`. Ikke endre historiske rapporter eller pinned fixtures.

Behold testene for dagens image-bygging og pull-feil. Legg til målrettet dekning
av at nginx ikke bygges, men oppdages og hentes gjennom eksisterende pull-flyt,
og at øvrige app-builds bruker samme tags og contexts som før. Verifiser renderet
proxy-YAML, runtime-templating/DNS, bevarte
nginx-variabler, image-inkludering i offline-bundle og uendrede TLS-/rutemounts.
Oppdater tester som tidligere leste `apps/proxy/default.conf`, uten å svekke
kontrollene for separate komponenter og dynamiske ruteregistreringer.

Kjør produkttester, acceptance-harness-tester, ruff, formatkontroll, pyright,
vermin, shellcheck og `git diff --check` med repoets oppsett. Oppdater relevante
releaseversjoner etter repoets regler, uten å endre uendrede app-images/tags.
Dokumenter at app-byggingen er uendret, og hvordan standard nginx hentes og
proxyen konfigureres fra YAML. Beskriv nødvendig
labverifikasjon av HTTPS, innlogging, platform/help uten Identity, app-tillegg,
DNS etter restart, helse og offline installasjon. Ikke reset labmiljøer uten
autorisasjon og ikke påstå at stubbede tester beviser faktisk nginx/Podman-atferd.

Ingen config-/credential-migrering, fallback for gammel proxy-layout,
passordrotasjon, ny komponentmodell eller bred deploy-refaktorering. Behold
persistente config-/credential-bytes, databasedata, retry og SELinux-/fapolicyd-
kontroller. Rapporter endrede filer, valgt YAML-/entrypoint-løsning, faktiske
testresultater og verifikasjonshull.

## 19. Remove branches whose changes are already in main

Status: done. On 2026-10-17 `git ls-remote --heads origin` listed only `main`;
`fix/atomic-install-records` and `improvements-0-2` no longer exist on the remote.
Their content was confirmed in `main` on 2026-10-16 as described below. Who deleted
them is not recorded here. No source, release version or `main` history changed.

Melding til agenten:

Rydd opp i de to branchene `fix/atomic-install-records` og `improvements-0-2`
i `gunstein/podman_offline`. Behold `main`.

Ved kontroll 16. oktober 2026 var `improvements-0-2` inkludert i historikken til
`main`. De tre commitene på `fix/atomic-install-records` var samlet i commit
`c1e26e2369c94350aae36ead018fc5f82117ffc0` på `main`, med identisk innhold i de
tre berørte filene. Den branchen trenger derfor ingen ekstra merge.

Hent oppdatert remote-status før sletting og kontroller at ingen av branchene
har fått nye endringer som mangler i `main`. For atomic-install-records må
kontrollen ta høyde for at endringene er samlet i én commit; manglende felles
commit-ID alene betyr ikke at innholdet mangler. Hvis nytt arbeid mangler i
`main`, rapporter dette og behold den aktuelle branchen.

Slett bare de to navngitte remote-branchene når innholdet er bekreftet ivaretatt.
Rydd eventuelle tilsvarende lokale brancher og foreldede remote-referanser uten
å miste lokale endringer. Ikke endre kildekode, releaseversjoner eller historikk
på `main`, og ikke opprett en ny merge bare for å markere branchene som merget.
Rapporter hvilke brancher som ble slettet og hvordan innholdet ble kontrollert.

## 20. Make components and bundles declarative instead of hardcoding demo names

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: done in 0.4.9 (merged from `feature/declarative-components`); local
product and harness tests pass, and the lab runs (demo and
`--renamed-product`) were CLEAN PASS on `8e62153`. See
[verification](acceptance/DECLARATIVE-COMPONENTS.md) and
[components](docs/COMPONENTS.md). The original task follows.
This addresses custom installations failing when a component is renamed, for
example from `identity` to `my-identity`. Component IDs currently reject `_`;
retain the existing lowercase/digit/hyphen rule and explain it clearly.

### Analysis of the current implementation

The current component model is fixed in `deployment/common.py` through
`DEPENDENCIES`, `COMPONENTS` and `VERSION_FILES`. `bundles.yaml` is validated
against that model rather than defining it. Changing a directory or the YAML
alone therefore cannot define a new component.

Name-dependent behavior also exists in:

- `deployment/deploy.py`: config initialization and platform config inheritance;
  dev preparation; bundle selection and dependency/version checks; registration
  staging; allowed client directories; fixed import IDs; registration owner
  restarts; pending-state validation; install markers; uninstall dependents and
  registration-owner updates.
- `deployment/render.py`: compulsory PUBLIC_ORIGIN/HTTPS_PORT for every component
  and deriving PUBLIC_HOSTNAME only for the literal platform name.
- `deployment/cli.py`: fixed component validation and the special platform
  argument to uninstall.
- `bundle.py`: component admission, version-file selection, dependencies and
  generated bundle descriptors.
- `dev/dev.sh`: three named databases, a named platform config and five named
  components passed to the certificate script.
- `scripts/generate-certificates.sh`: demo component names, certificate paths,
  signing material and demo users. This is application-specific provisioning,
  not a requirement every deployment should inherit.

Image delivery is already mostly independent of app sources: `bundle.py` and
production deploy do not need `apps/`; registry images are discovered from YAML.
`dev/build-images.sh` is a demo build helper with an explicit naming convention.
Demo source code, OIDC routes and smoke tests may legitimately name demo apps.
They must not determine which components the general deployment tools accept.

The most sensitive part is lifecycle metadata across isolated offline bundles.
The source catalog is unavailable on the target, and another component's release
may have been removed. Reverse dependencies, registration ownership and pending
work must remain understandable from validated bundled/installed metadata.
Replacing constants with a source-file lookup everywhere would not solve this.

### Review findings explicitly included in item 20

The subsequent Python review confirmed that this task must also cover:

- Bundle validation/version sources must come from declarations, not
  `common.COMPONENTS`, `DEPENDENCIES` or `VERSION_FILES`. The initial image
  discovery/validation in `bundle.build()` must use the selected catalog too;
  an unselected directory with an invalid image must not block a selected build.
- Registration owners, owner import IDs, allowed client directories, restart
  order and config inheritance must not depend on demo component names.
- A component without a public endpoint must not require PUBLIC_ORIGIN or
  HTTPS_PORT. Deriving PUBLIC_HOSTNAME must not depend on the name `platform`.
- Document and test the OIDC contract explicitly: currently client ID equals
  component ID, base_path equals `/` plus that ID, and scopes equal
  `[openid, profile, component ID]`. Separate configurable application identity
  from deployment identity where the existing application protocol supports it;
  otherwise validate and document that protocol constraint explicitly. Never
  silently overwrite a supplied descriptor with inferred demo values. Supporting
  arbitrary new OIDC protocols is outside scope.

Add targeted regression tests for these cases alongside the required renamed-app
unit and acceptance scenarios below. Item 21 separately handles preflight/render
ordering, resource-kind validation and registration removal. Item 7 owns broader
PostgreSQL mount-layout support; do not expand either task into that work.

### Message to the implementing agent

Make component selection and lifecycle behavior in `gunstein/podman_offline`
declarative. A user must be able to define their own components under
`components/` and in `bundles.yaml`, use externally built images and run dev,
build bundles and install them offline without editing Python or shell code to
add/rename components. Treat the shipped five components as one demo product
configuration, not a built-in platform model.

Read the current repository and any AGENTS.md first. Inspect the files and
functions identified above, the dependency/retry/registration tests, config
precedence, certificate preparation and existing image/bundle helpers. Work from
the actual branch; recent changes include Secret source-level generation,
standard nginx from YAML and app1 database init. Preserve these behaviors.

### 1. Define one authoritative source model

Choose a small, explicit YAML schema. `bundles.yaml` selects the components to
package/run, and their directories provide defaults/manifests. Put component
metadata in that YAML or in one referenced descriptor per component; do not
maintain duplicate independent graphs in Python and YAML.

The model must express, where relevant:

- Component ID and selection, dependency IDs and compatible version rules.
- Release version source and the existing install/upgrade behavior (including
  unchanged-version shared-component handling), without inferring behavior from
  an ID or from the existence of a particular version filename.
- Route and OIDC-client registration owners and their destination VOLUME_FILES
  resource IDs. Route changes and client changes remain different operations.
- Any explicit config inheritance/equality contract, such as a component taking
  PUBLIC_ORIGIN and HTTPS_PORT from its declared gateway dependency.

Use one component per bundle as today, with bundle/component IDs matching, unless
inspection reveals a concrete requirement otherwise. Multi-component bundles,
new plugin systems and arbitrary executable hooks are outside this task.

Keep metadata declarative and validate it before writes, credential generation,
image operations or service changes. Reject duplicate YAML keys, invalid IDs,
unknown dependencies, self-dependencies, cycles, conflicting owners, missing
selected directories/files, unsafe paths and inconsistent resource ownership.
Version-file paths must remain confined to the source/release; reject traversal
and symlink escape. Report the filename/component and expected declaration, not
an unhandled FileNotFoundError.

Define the directory-selection rule explicitly: selected catalog entries require
matching component directories; unselected directories must not be installed or
built implicitly. A bare directory must not silently invent missing dependency
or ownership metadata. Topologically order selected components, with a stable
order for unrelated nodes. Preserve manifest order within each component.

Keep component IDs restricted to the existing safe naming rules. Explain that
`my-identity` is valid and `my_identity` is not; do not silently rewrite names.
Do not introduce a renamed default component list as a fallback.

### Declarative addition and removal of services

Adding a service must require only a new directory under `components/` containing
its supported YAML manifests, defaults/metadata, and an update to `bundles.yaml`.
Use existing version sources or declare version data in YAML; do not require a
new Python constant, shell case, handwritten service inventory or new per-service
version file. Existing images and externally supplied credentials may still need
normal preparation. This requirement concerns service discovery and lifecycle,
not automatic application image building or certificate issuance.

Removing a service from the source product must require only removing its catalog
entry, updating affected YAML dependencies/roles, and removing its component
directory. Dev output, discovered images and new bundles must then exclude it,
including after a previous prepare/build in the same working directory. Stale
rendered artifacts or distributions must not make removed services part of the
current generated product; clearly distinguish retained historical archives from
current build outputs. An entry whose selected directory is missing is an error,
not an implicit removal. A still-declared dependency on the removed service must
fail clearly before side effects.

Removing source declarations does not authorize uninstalling an already-installed
production service or deleting data. Preserve installed dependency/registration
metadata; removal on a target uses explicit uninstall with its existing data
retention and dependency rules. Ensure that offline uninstall remains available
from the service's previously built bundle even when its source directory/catalog
entry no longer exists. Do not silently prune installed components absent from a
new source catalog. Document how to stop removed dev services through the normal
dev lifecycle without deleting their persistent data or unrelated containers.

Add unit/product tests that add and then remove a custom service by changing only
component files and `bundles.yaml`, with no edits to generic Python/shell code.
Cover fresh and repeated prepare/build, stale-output exclusion, dangling dependency
errors, unaffected siblings and preservation of installed production state.
Extend runnable acceptance coverage to add/start/use the service, stop it through
the normal dev lifecycle, remove its source definition and rebuild/restart the
remaining dev product; verify it is absent from the new product and siblings
still work. Also verify explicit scoped offline uninstall using its retained
bundle after source removal, with ordinary uninstall preserving data. Report
actual runtime execution separately from harness/unit results.

### 2. Support isolated production bundles and installed metadata

Compile the required validated metadata into `bundle.yaml` (or a minimal bundled
catalog). An unpacked bundle must support init-config/install/uninstall without
source `bundles.yaml`, sibling source directories, `apps/`, or the original
checkout. Its own payload remains component-scoped.

Persist enough public metadata to discover installed dependents and registration
owners independently of the incoming source catalog and retained release files.
Read installed metadata with the same strictness as current dependency records;
do not infer installed components from arbitrary home directories. Keep the
existing atomic ordering: dependency/ownership metadata is durable before the
installation completion marker makes a component available.

Preserve version range checks, missing/incompatible dependency refusal, reverse
upgrade checks, downgrade refusal and uninstall dependency guards. A component
with pending uninstall is not an available dependency. Adding a component to a
new source catalog must not hide an already-installed dependent or erase its
registrations because it is absent from that source checkout.

Define how conflicting owner/config metadata is rejected. Do not let a newly
supplied descriptor silently reassign another installed component's registrations
or state. Keep bundle checksums and validation of untrusted paths/names.

### 3. Resolve registration behavior through declarations

Replace literal platform/identity owner selection and fixed `platform-routes` /
`identity-clients` import IDs with validated metadata. Existing nginx route and
Identity client formats can remain supported protocols; their component IDs
must be arbitrary. No change to demo application protocols is required.

The existing demo may retain its component names, resources, URLs and OIDC IDs.
A renamed test product must be expressed through YAML/config/application
inputs, with no edits to generic deploy code. Retain strict public descriptor
validation, public-certificate handling and protection against importing private
keys. Keep existing client URL/scope conventions where needed; do not turn this
into an arbitrary OIDC integration framework.

Remove the app1/app2-only client-directory allowlist. Validate registered clients
against authoritative installed/pending metadata and their public descriptors.
Continue rebuilding the current route/client indexes so removed entries do not
remain active due to stale imported files.

Restart only affected owners. No change means no owner restart; route-only means
route owner; client-only means client owner; both means both. Never restart
sibling applications as a side effect. Order restarts by declared dependencies,
not a literal pair of owner names. No declaration of routes or OIDC must mean
no requirement for either service.

### 4. Generalize config, dev and CLI

Remove the unconditional requirement to load platform config during every
installation. A standalone worker or service with no gateway, Identity, database
or public URL must work with only its own required manifest placeholders/config.
Validate shared URL/port rules only for components declaring that contract.
Handle derived values such as PUBLIC_HOSTNAME through the relevant declared
behavior or validated config, rather than a test of the component's name.
Preserve common/component/dev precedence and authoritative persistent production
config. Keep init-config an explicit operation; do not implement automatic
init-config as part of this task.

Run manifest-driven database preflight for selected components before any secret
creation. A component without PostgreSQL needs no database settings. Keep the
current PostgreSQL layout checks and lost-password/existing-volume refusal;
broader database image/layout support remains backlog item 7.

`dev/dev.sh up/down` and `./deploy prepare` must use the catalog and dependency
order, including the real app1 database-before-init order. Generic dev startup
must work with a missing/empty `apps/` and externally prepared credentials/images.
It must not invoke demo certificate/user generation for arbitrary components.

Separate demo provisioning explicitly: the existing certificate/demo-user logic
may remain in a clearly identified demo helper with an explicit documented call.
Do not rename or rotate existing demo credential files merely to achieve this.
Keep a simple documented command sequence for starting the shipped demo. Do not
introduce implicit arbitrary script execution from YAML as a shortcut.

Generalize CLI component arguments from validated bundle/catalog metadata.
Retain the existing root commands and `--delete-data`. A production bundle must
still refuse operations on another component. Document generic syntax and remove
special treatment of a literal platform argument.

### 5. Keep image building independent

Continue discovering ordinary and init-container images from manifests.
A selected set of registry-image components must build offline bundles and run
dev without an `apps/` directory. Build/pull/image discovery must use the same
selected component set as prepare, not all stray directories under components/.

Keep the current demo image build helper or clearly label it as demo-specific.
Do not add a Python image-builder refactor or automatic build fallback. Local
images must be explicitly prepared; external registry images use existing pull
and offline save/load behavior. Do not fetch code/packages/images on targets.

### 6. Preserve retries, isolation and safety

Adapt pending-state validation to declared/installed component IDs and owners.
Retain durable registration work recorded before writes, regenerated import
archives, owner checks and acknowledgement only after success. A retry must work
in a fresh process even when files already match or the source release is gone.

Uninstall must retain its validated component-scoped volume plan, including
mounted ConfigMaps, after deleting YAML. Keep flag-conflict refusal, missing
volume handling versus inspection errors, dependency guards and private atomic
state writes. No operation may clear another operation's pending work.

Preserve current credentials, generated-file byte retention, resource prefixes,
Secret/PVC names, container mounts, data isolation, symlink/path protections,
logging hygiene, SELinux/fapolicyd checks and offline checksum guarantees. Reject
invalid declarations before destructive side effects.

There are no existing installations requiring an upgrade to this metadata
schema. Implement only the new source/bundle/installed metadata layout. Do not
add migration code, legacy aliases, old-schema fallbacks or automatic state moves.
Use fresh isolated state in tests, then exercise normal restart/redeploy/retry
within that new model. Keep historical evidence and pinned release fixtures.

### 7. Required verification

Keep the existing demo regression suite and add focused tests demonstrating:

1. A fully renamed product, for example `gateway`, `login-service`, `orders` and
   `manual`, with renamed resources and separate route/client owners, operates
   without changing Python/shell source. No former component directory exists.
2. A minimal component such as `worker`, with no dependencies, PUBLIC_ORIGIN,
   HTTPS_PORT, database, registration provider, certificates or apps directory,
   supports prepare, bundle, init-config, install and uninstall.
3. Adding a valid new catalog entry/directory requires no code edits. Unselected
   directories are excluded from images, dev output and bundles.
4. Dependency order is deterministic; missing nodes/cycles/duplicate IDs/unsafe
   paths/ambiguous roles fail before writes or host commands. Error messages
   explain the actual declaration error.
5. Offline bundles work from another directory with no source catalog/sibling
   releases. Installed reverse dependencies and version contracts remain enforced
   even if the incoming bundle's source did not contain those dependents.
6. Renamed clients survive another component's install/upgrade/uninstall;
   route-only/client-only/both/no-change restart sets remain exact.
7. Registration write, import write and owner restart/check failures are retried
   in fresh processes with the new IDs. Partial uninstall/data deletion resumes
   after rendered YAML removal and preserves unrelated state.
8. The original demo still passes credential, database, init-container, nginx,
   image/build, checksum, config precedence, isolation and wrapper tests.
9. Registry-only dev/bundling requires no apps directory or demo provisioning;
   the explicitly selected demo bootstrap still provisions its original layout.

Renaming coverage is mandatory at both levels:

- Unit/product tests must rename application components as well as the gateway
  and Identity components. Use at least two renamed apps (for example `orders`
  and `inventory`) to verify selection, dependencies, rendering, client/route
  registration, exact restart sets, retries and isolation from the sibling app.
  Change only declarative configuration/component fixtures, never generic
  Python/shell code. Do not merely test renaming Identity.
- Add executable real acceptance scenarios to the existing harness for this
  renamed product. From fresh isolated state, exercise dev startup and the
  offline production lifecycle: bundle creation, explicit init-config,
  dependency-ordered install, access through the proxy, OIDC login and database
  CRUD for both renamed apps, restart/redeploy with persisted data, and
  component-scoped uninstall. Verify app init-container behavior where declared.
  Run the offline target portion without source checkout or original component
  directories. Application images may be reused with declarative runtime inputs;
  the scenario must not require code patches to accept the new component IDs.
- Include harness tests for scenario wiring, assertions and failure reporting.
  These complement but do not replace real Podman/systemd acceptance runs.

Implement these acceptance scenarios even if the execution environment cannot
run them. Document the exact commands, prerequisites and expected assertions so
an operator can run them later. Report unit/product results, harness results and
real acceptance results separately; unavailable lab access means runtime
verification is outstanding, not that acceptance coverage may be omitted.
Renaming here means defining a fresh installation with different component IDs,
not migrating an existing installation's names or state.

Run all product and acceptance-harness tests, ruff, format, pyright, vermin,
shellcheck and git diff --check with the project's existing setup. Keep host
Python 3.6 compatibility. Adapt generic acceptance inventory/packaging as needed
and retain existing demo login/CRUD scenarios alongside the renamed-app scenarios.

If authorized lab access is available, verify fresh installs and lifecycle for
both the shipped demo and a renamed/minimal fixture. Otherwise give exact
remaining lab scenarios. Do not reset other environments, claim stubbed tests
prove Podman/systemd behavior, or count historical runs as current evidence.

### Architecture boundary and complexity check

Moving the component model from Python constants into declarations is the scoped
architecture change in this task. Keep the current module structure as the
starting point; a wider architectural rewrite is not required by these findings.
Organize the flow around three explicit responsibilities:

1. Read and validate one authoritative component model from YAML.
2. Plan dependencies, registration changes and required service restarts using
   that validated model, without performing those actions.
3. Execute the plan through the existing lifecycle functions, preserving durable
   pending work and retry guarantees when an action fails.

Use small functions and explicit data within the existing modules where practical.
These responsibilities do not require new layers, a plugin system, a class
hierarchy, a generic operation engine or a transaction framework. Introduce a
small helper module only when it gives a concrete readability benefit and explain
that choice; do not reorganize the package merely to mirror these three steps.

If implementation starts accumulating many mode flags, parallel representations
of the same model, or special cases, pause implementation to reassess and simplify
the design before continuing. Do not conceal growing complexity with additional
abstractions. The understandability review must assess these warning signs and
justify any remaining complexity before the task can be marked complete.

### Mandatory understandability review

Before marking this task complete, perform and report an explicit
understandability review of the final diff, separate from automated checks.
A moderately experienced Python developer must be able to follow the normal
flow and failure/retry paths without reconstructing hidden conventions.

- Trace one successful operation and one failure/retry from CLI entry to durable
  state and service actions. Explain which function owns each step and why its
  ordering is safe.
- Identify the single source of truth for each decision. Avoid duplicate models,
  hidden defaults, name-based special cases and unnecessary indirection.
- Prefer small named functions, explicit data and ordinary control flow. Do not
  introduce a plugin system, operation engine or class hierarchy for these fixes.
- Check that validation, planning and side effects are visibly separated, with
  clear state ownership and completion conditions. Comments should explain why
  an ordering or constraint matters, rather than repeat the code.
- Simplify confusing paths before delivery. Report remaining complexity and its
  concrete justification, plus any simplifications made during this review.
  Passing tests alone does not satisfy this completion requirement.

### 8. Documentation and delivery

Document the final YAML schema, selection rules, dependency/version contracts,
optional registration/config roles, installed metadata, explicit demo bootstrap
and a complete example of adding a custom component using an external image.
Explain the source catalog versus compiled bundle metadata versus installed
metadata; distinguish component IDs, image names, resource names and public URLs.

Search active generic code for the former component names and explain every
remaining match. Names are acceptable in demo configuration/application code,
explicit demo provisioning/smoke tests, tests and historical evidence; they must
not restrict the generic tool's supported components. Do not replace literals
with indirect demo-specific conditionals or silently default to the demo graph.

Report the original coupling, selected schema and rationale, changed files,
verified custom/demo scenarios, test results, runtime gaps and confirmation that
no migration/fallback was added. Apply repository release version rules.
Favor small explicit functions and one validated metadata model over a generic
plugin framework or large object hierarchy.


## 21. Fix manifest validation gaps and removal of obsolete registrations

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: implemented in 0.4.10 on `feature/manifest-validation`; local checks
green, and all six lab scenarios were CLEAN PASS on `5ee9748`. See
[verification](acceptance/MANIFEST-VALIDATION.md). Original findings: four,
reproduced in isolated Python checks.

### Message to the implementing agent

Fix the following four concrete issues in `gunstein/podman_offline`. Read the
current branch, AGENTS.md if present, and relevant product/harness tests first.
Item 20 may have changed the component model before this task starts: use the
actual declarations and lifecycle implementation, not a historical hardcoded
graph. Keep this work separate from general component/schema refactoring.

### 1. Validate the effective database manifest

`deployment/deploy.py: database_preflight()` currently reads raw YAML. A PVC
reference `claimName: "@@DB_VOLUME@@"` results in the literal command
`podman volume exists @@DB_VOLUME@@`, rather than checking the configured volume.
This was reproduced with a mocked subprocess; the actual Podman response to that
invalid name has not been measured. Do not claim this reproduction proves real
Podman would report the volume absent.

Resolve supported whole-value placeholders using the authoritative effective
config before database inspection. Apply the same resolved manifest values that
will be rendered and installed. Do not call the side-effecting renderer just to
obtain them. Validate resolved names, bindings and required values before host
commands or generation. Missing/invalid placeholders must fail clearly.

Test both literal and configured PVC names, Secret references and password-file
paths supported by the existing layout. Assert the actual name passed to Podman.
With a missing password and the resolved volume present, fail without creating a
password or changing runtime state. Cover absent volume and inspection errors
separately: only the documented absent-volume result allows generation. Preserve
existing password bytes and normal config precedence. Broader PostgreSQL images,
PGDATA layouts and mount support belong to item 7, not this fix.

### 2. Make supported resource kinds consistent across the lifecycle

Current database preflight and component resource-name checks recognize top-level
Pod documents, while image discovery and some render checks traverse nested pod
specs. A Deployment containing the same database spec therefore bypasses
preflight; a Deployment named for another component also passes the current
component-name check. Both behaviors were reproduced without running containers.
Uninstall also extracts mounted ConfigMaps only from top-level Pods.

Establish and document the resource kinds the tool actually supports. Either
handle a kind consistently in preflight, rendering, component isolation, image
collection and uninstall planning, or reject it clearly before side effects.
Do not add broad Kubernetes support as part of this task. Prefer explicit
rejection where support cannot be justified by existing product requirements and
Podman behavior. Account for wrapper/list documents so they cannot bypass checks.
Reuse a small explicit traversal/validation helper if useful; avoid a new generic
resource framework. Check names after substitution and preserve scoped volume
ownership checks.

Test identical relevant container specs under each supported wrapper. For
unsupported kinds assert an actionable error before generation, Podman calls,
registration changes or service changes. Cover foreign resource names, database
checks, init-container validation, image discovery and mounted ConfigMap cleanup
as applicable. Preserve existing supported fixtures or explicitly update their
contract; do not silently accept documents only part of the lifecycle understands.

### 3. Remove registrations omitted by a new release

`registration_stage()` copies installed routes/clients before applying incoming
files. If an installed app's new release removes `route.conf`, the old route is
still imported and no change is recorded. The old-route case was reproduced;
client.yaml follows the same retention logic and needs its own regression test.

For the component being installed/upgraded, treat the incoming release's declared
registration set as authoritative. If its previous route or client is absent in
the new release, stage removal, rebuild the public indexes/imports and restart
only the affected registration owner. Preserve all sibling registrations.
Absence for a component not selected by this operation must never mean removal.

Extend the existing explicit registration change/pending mechanism to represent
removals safely. Record required owner work durably before deletion can hide the
change. After any failed import write or owner restart/check, retry in a new
process must rebuild the required imports and finish owner work even though the
old registration has already disappeared. Do not add a transaction framework,
rollback, or untracked deletion shortcuts. Preserve private path/symlink checks.

Test route-only removal, client-only removal, both removals and unchanged inputs;
assert exact owner restarts, updated indexes, retained sibling entries and no
sibling app restart. Inject failures after deletion and during archive writing
and owner restart/check. Retry with the same persistent directory in a fresh
process, and verify pending state is removed only after success. Test ordinary
uninstall still works with registrations already removed by an earlier upgrade.

### 4. Validate manifests before generating secrets

`materialize_and_render()` currently calls generate_secrets before checking pod
mounts and final resource links. A manifest referencing an undefined volume was
rejected, but its declared generated password had already been created.

Separate side-effect-free structural/config validation from materialization.
Resolve placeholders and validate supported kinds, resource names, duplicate
resources, volume mounts, offline image policies and declared Secret/PVC/ConfigMap
links before generating files or writing import archives/output. Validate what
can be determined from declarations first; checks requiring generated file bytes
may follow generation. Do not promise transactionality for arbitrary filesystem
failures or implement rollback that deletes existing credentials.

Add tests for invalid mounts, missing references, duplicate resources, invalid
policies and unresolved placeholders. Snapshot fresh state and existing config/
credential bytes and assert those validation failures produce no new secrets,
archives, output YAML, registration changes or host actions. Retain positive
coverage for valid generation, file-content validation and byte-preserving
restart/redeploy. Keep database-preflight before secret generation.

### Mandatory understandability review

Before marking this task complete, perform and report an explicit
understandability review of the final diff, separate from automated checks.
A moderately experienced Python developer must be able to follow the normal
flow and failure/retry paths without reconstructing hidden conventions.

- Trace one successful operation and one failure/retry from CLI entry to durable
  state and service actions. Explain which function owns each step and why its
  ordering is safe.
- Identify the single source of truth for each decision. Avoid duplicate models,
  hidden defaults, name-based special cases and unnecessary indirection.
- Prefer small named functions, explicit data and ordinary control flow. Do not
  introduce a plugin system, operation engine or class hierarchy for these fixes.
- Check that validation, planning and side effects are visibly separated, with
  clear state ownership and completion conditions. Comments should explain why
  an ordering or constraint matters, rather than repeat the code.
- Simplify confusing paths before delivery. Report remaining complexity and its
  concrete justification, plus any simplifications made during this review.
  Passing tests alone does not satisfy this completion requirement.

### 5. Review findings added after item 20 (2026-10-17)

An independent review of item 20 at `c00865f` reproduced §1–§4 with renamed
components (`orders-data` behind `@@DB_VOLUME@@`, a `Deployment` named
`gateway-stolen` installed from the `orders` bundle, an `inventory` release
without its route leaving `/stock` active, and a password generated before an
undefined mount was rejected). It also found:

- **F2:** `database_preflight` recognizes PostgreSQL only through
  `POSTGRES_PASSWORD_FILE` in top-level Pod `containers`. A container using
  `POSTGRES_PASSWORD` (for example through `secretKeyRef`) skips the check, so a
  lost password with an existing volume generates a new one silently. Refuse,
  before generation, every `POSTGRES_PASSWORD*` form other than the supported
  layout, with the file and container named; broader layouts stay item 7.
- **Root cause and suggested shape:** six places walk manifests with their own
  idea of the resource kinds (placeholder collection, references, pod-spec
  checks, image discovery, database preflight, the uninstall ConfigMap plan),
  and `materialize_and_render` renders twice per install. One pure function
  returning the effective, placeholder-replaced documents, plus one `pod_specs()`
  helper with an explicit list of supported kinds, used by all of them before
  `generate_secrets`, addresses §1, §2, §4 and F2 together. Extracting
  `uninstall_plan()` and one shared restart-and-acknowledge helper would make
  the lifecycle easier to follow. No wider architecture change is needed.

### Implementation plan (2026-10-17, revised after review)

Status of the plan: carried out in five commits. Deviation: imported
registration volumes are validated by name from the descriptor's `accepts`,
so staging stays where it was in install (after the preflight, before
generation); dev validates every component before writing its configs.

**Starting point.** Six places walk manifests with their own idea of resource
kinds: `check_component_names`, `database_preflight` and uninstall look only at
top-level `kind: Pod`; `check_pod_spec`, `find_images` and `references` search
for `spec`/`containers` at any depth. That mismatch is the root cause of §2 and
F2 and part of §1. `materialize_and_render` mixes validation with side effects,
derives `PUBLIC_HOSTNAME` internally, runs twice per install (and twice in
`install_standalone`) and calls `generate_secrets` before mounts and links are
checked (§4). `registration_stage` copies every installed registration,
including those of the component being upgraded (§3).

**Resource-kind contract.** Supported: `Pod`, `ConfigMap`,
`PersistentVolumeClaim`, `Secret`, which are the kinds the demo uses and
`podman kube play` handles well. Everything else (`Deployment`, `List`, an
unknown `kind`, a non-map document) is rejected with file and kind named before
any side effect, and already at `./build-bundle.sh`. No broader Kubernetes
support. `references()` stays recursive on purpose: a link is a link wherever
it appears in a supported document.

**Validation order, the same on every path.** Install, `prepare` (dev),
`prepare_standalone` and `install_standalone` all follow:

1. effective config (`render.effective_config`: merged config plus derived
   `PUBLIC_HOSTNAME`; the authoritative effective config §1 asks for);
2. effective documents (`render.effective_documents(config, manifests,
   component)`: placeholders replaced, kinds, names, pull policy, mounts; pure);
3. registration staging in a temporary directory (no live writes) when the
   path has registrations;
4. links and duplicates (`check_links`) once imports are known;
5. database preflight on the effective documents (the first host command,
   `podman volume exists`);
6. `generate_secrets`, then checks that need generated bytes (file-group
   content, empty/invalid password file), then output and archives.

A validation failure in 1–4 therefore causes no host command, generation or
write. In install, staging moves before preflight; staging writes only to its
temporary directory.

**Five steps, one commit each, tests green after every step:**

1. **One manifest model (§2).** `render.check_kinds(documents, source)` with
   `SUPPORTED_KINDS`, and `render.pod_specs(documents)` yielding
   `(document, spec)` for Pods. Use them in `check_pod_spec`, `find_images`,
   `check_component_names`, database preflight, the uninstall plan and
   `bundle.manifest_images`; drop the any-depth search. Tests: the same
   container spec is accepted in a Pod and rejected in a Deployment/List
   before Podman calls, generation or writes, including at build; a
   `Deployment` named `gateway-stolen` is rejected.
2. **Validation before side effects, one render (§4).** Add
   `effective_config` and `effective_documents` (above) and make
   `materialize_and_render` a thin sequence of steps 4 and 6. Render once per
   component: return the rendered text together with the volumes to archive,
   so `write_component_units_and_imports` and `install_standalone` only write.
   Apply the validation order to all four paths. Tests: invalid mount, missing
   reference, duplicates, wrong pull policy, unreplaced placeholder on each
   path, each with no new secrets, archives, YAML or host commands and
   existing config/credential bytes unchanged.
3. **Database preflight on the effective manifest (§1, F2).**
   `database_preflight` takes the effective documents and uses `pod_specs`,
   so Podman receives the configured volume name, not `@@DB_VOLUME@@`. Split
   the ~110-line function into small named helpers (find the PostgreSQL
   binding, find the password file, check the volume). F2: refuse every
   `POSTGRES_PASSWORD*` form other than the supported `POSTGRES_PASSWORD_FILE`
   layout, including `secretKeyRef`, in `containers` and `initContainers`,
   naming file and container; other layouts stay item 7. Tests on the install,
   dev and standalone paths: literal and configured volume names with the
   exact Podman argument; absent volume (exit 1) allows generation; existing
   volume (exit 0) and inspection errors (other exit, `OSError`) refuse
   without generating; existing password bytes preserved.
4. **Registrations removed by a new release (§3).** In `registration_stage`
   the release files are authoritative for the selected components: their
   installed route/client is never copied, whatever their declared roles.
   A dropped role is returned as a separate set,
   `removals = {"routes/<id>.conf", "clients/<id>"}`, rather than `None`
   values in `updates` (a client is a directory, `updates` is per file).
   `registration_changes` counts an existing removal target as a change for
   its owner; pending owners are saved with `save_pending` before
   `write_registrations` deletes, with the same symlink checks, using the
   existing pending mechanism and no transaction logic. Retry in a fresh
   process rebuilds indexes without the deleted entry and restarts the
   pending owners. Absence for an unselected component never means removal.
   Clean-up: extract `uninstall_plan(component, output)` and one shared
   `restart_and_acknowledge(owner, state)` used by install and uninstall.
   Tests: route-only, client-only, both and unchanged; exact owner restarts,
   siblings kept and not restarted; failures injected after deletion, during
   archive writing and during restart, then retry in a fresh process;
   uninstall after an upgrade already removed the route.
5. **Acceptance, docs and version.** Extend the existing `--renamed-product`
   scenario instead of adding one with its own VM reset: at the end, generate
   an inventory release with a higher version and without `route.conf`,
   `client.yaml` and the catalog's `routes`/`clients`, install it, and check
   that `/stock` returns 404, the inventory client is gone and orders still
   works. Update `docs/COMPONENTS.md` (supported kinds), `ARCHITECTURE.md`
   (sequence diagram: validation order) and `docs/REVIEW_GUIDE.md`. Bump the
   product version per the repository's rules. Write
   `acceptance/MANIFEST-VALIDATION.md` with the mandatory understandability
   review.

**Trade-offs.** Rejecting `Deployment` is simpler than supporting it, and no
existing requirement needs it. No classes or frameworks: a few small functions,
fewer lines overall as six traversals become one. Validation that needs
generated bytes still runs after generation; document that explicitly.

**Delivery.** Branch `feature/manifest-validation`, five commits, one PR (as
for item 20), reviewable commit by commit. Step 2 is the largest and riskiest;
if smaller reviews are preferred, split into two PRs after step 2 (model and
validation; then preflight, removal and acceptance).

### Scope, verification and delivery

- Preserve Python 3.6 support for host tools, existing commands, authoritative
  persistent config, credentials, checksum/offline guarantees, retry behavior,
  SELinux/fapolicyd handling and component isolation.
- No migration, legacy fallback, credential rotation or general architecture
  refactor. Use fresh isolated fixtures; retain historical evidence unchanged.
- Run product tests, acceptance-harness tests, ruff, format checks, pyright,
  vermin, shellcheck and git diff --check using the repository setup.
- Add a focused runnable acceptance regression for registration removal on
  upgrade: verify the removed route/client is no longer active, while a sibling
  remains usable. Reuse existing lab setup and avoid duplicating item 20's full
  renamed-product suite. Keep failure injection tests as the primary coverage
  for precise retry boundaries and preflight command selection.
- Run relevant real Podman/systemd scenarios only in an available authorized
  isolated environment; never reset unrelated installations. If unavailable,
  implement/document the scenario and exact operator commands and report it as
  unexecuted. Stubbed tests do not prove actual runtime behavior.

Report each root cause, chosen resource-kind contract, changed files, regression
coverage, actual checks/results and remaining runtime gaps. Explain how removal
work survives retry and which validation necessarily requires generated bytes.
Apply the repository's release/version rules when implementing the fixes.

## 22. Introduce mutation testing for the deployment tools

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its section on
assessing evidence, including the tests themselves.

Status: planned. No mutation tool, configuration or results exist yet.

### Background

The suites pass, but passing tests do not show that they would detect a wrong
decision. The review guide already warns that a mock accepting any volume name
does not verify that the correct volume was inspected. Mutation testing makes
that gap measurable: it changes the code in small ways (a `<` becomes `<=`, a
condition is negated, a call is removed) and reports which changes no test
detects.

### Message to the implementing agent

Introduce mutation testing in `gunstein/podman_offline` as a development tool.
It is not a runtime dependency and not something shipped in bundles. Read
AGENTS.md, the review guide and `tests/README.md` first, and use the current
module layout after items 20 and 21.

1. Choose one maintained Python mutation tool that runs on the development
   Python version (for example mutmut or cosmic-ray), and give the reason for
   the choice. Pin its version as a development requirement next to the
   existing lint/type tools. Host Python 3.6 compatibility of `deployment/`
   and `bundle.py` is unchanged; the tool itself need not support 3.6.
2. Start with the code where an undetected change is most harmful:
   dependency/version checks, catalog and descriptor validation, registration
   staging and owner restarts, pending-state handling, database preflight,
   generated-secret paths and uninstall volume plans. Exclude demo
   applications, acceptance-lab transport and logging/message text.
3. Run the existing product tests (`python3 -B -m unittest discover -s tests`)
   as the kill criterion. The run must stay offline and must not call Podman,
   systemd or the network; keep the existing stubs.
4. Add one documented command and configuration that a developer can run
   locally, with the expected duration and how to rerun a single module.
5. Record a baseline report: mutants per module, killed, surviving and
   timed-out. Classify each survivor as a missing test, an equivalent mutant
   (with a short justification), or code that can be simplified.
6. Add focused regression tests for the important survivors. Assert the
   arguments and state transitions that matter, not just the exit status.
   Do not change production behavior only to kill a mutant; simplifying dead
   or redundant code is allowed when the review guide's contracts hold.
7. Agree a threshold with the user before adding any automatic gate. Until
   then, report the score and do not make it block other work.

### Verification and delivery

Run the product tests, acceptance-harness tests, ruff, format, pyright, vermin,
shellcheck and `git diff --check` as usual. Report the tool and version, the
exact commands, the baseline and final mutation scores per module, the tests
added, the remaining survivors with their classification, and the run time.
Mutation results are evidence about the unit tests only; they do not replace
real Podman/systemd acceptance runs.

## 23. Explicit side-effect-free validation command for YAML, secrets, volumes and placeholders

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: planned. Requested 2026-10-17. Coordinate with item 21 §4, which moves
the same checks ahead of secret generation inside install; this item adds the
explicit command and reuses that validation instead of a second implementation.

### What exists today

The checks exist, but only as steps inside `prepare`/`install`, and partly after
side effects:

- `render.validate_component_config` requires every whole-value `@@NAME@@`
  placeholder in a component's manifests to exist in its config before writes.
  `render.replace` and the final `Unreplaced @@...@@` check catch the rest
  during rendering.
- `render.check_links` rejects a Secret/PVC/ConfigMap that a manifest uses but
  nothing defines, an id in `SECRET_FILES`/`VOLUME_FILES` that no manifest uses,
  and names defined twice. `render.check_pod_spec` rejects mounts of undefined
  pod volumes and a missing `imagePullPolicy: Never`.
- These run inside `materialize_and_render`, after `generate_secrets` and while
  reading the source files, so a failed check can leave a newly generated secret
  behind (item 21 §4). There is no command that only validates, and no check
  that reports every problem at once.

### Message to the implementing agent

Add one explicit validation command that a developer or operator runs before
`prepare`, `build-bundle.sh` or `install`, for example `./deploy validate`.

1. Scope: in the source checkout, validate every catalog component with its dev
   config layers (common, component, optional `config/dev.yaml`). In an
   unpacked bundle, validate the bundle's component against the persistent
   config, as install would. Standalone manifest fixtures keep their explicit
   `config.yaml`.
2. Checks, using the existing functions rather than a parallel implementation:
   YAML syntax and duplicate keys; supported resource kinds; component name
   prefixes; every `secretName`, `claimName`, ConfigMap name, `secretKeyRef`,
   `secretRef`, `configMapRef` and `configMapKeyRef` has a matching
   `SECRET_FILES`/`VOLUME_FILES` id, import volume or manifest resource; every
   config id is used; every `@@NAME@@` has a config value of the right type,
   including init containers; pod mounts and pull policy; Secret `items` keys
   that can be determined from declared file names or `generate` entries.
3. No side effects: no secret generation, no reads of private file contents
   beyond existence and type, no archives, no rendered output, no Podman or
   systemd calls, and no network. Missing declared source files are reported as
   such; `generate` entries count as present.
4. Report all findings in one run, each with file, document/container and the
   expected declaration, then exit non-zero. Never print config values or
   secret contents. Exit zero with a short summary when everything passes.
5. Make `prepare`, `install` and `bundle.py` call the same validation first, so
   the command and the lifecycle cannot disagree.

### Tests and delivery

Add focused tests for each finding type (missing Secret/PVC id, unused id,
undefined ConfigMap, missing and wrongly typed placeholder, placeholder only in
an init container, undefined mount, duplicate resource name) and assert that a
failing validation creates no files and runs no commands. Validate the shipped
demo and the renamed/minimal fixtures from item 20. Run product tests,
acceptance-harness tests, ruff, format, pyright, vermin, shellcheck and
`git diff --check`. Document the command in README and the review guide.

## 24. Optional disaster recovery (DR), adapted from podman_test

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: planned; large. Requested 2026-10-17. Requires a separate analysis and
an agreed plan before any implementation. Builds on item 20 (declarative
components) and should start after it has been merged; coordinate with items 2
(password rotation), 3 (backup and credential recovery, which this item may
absorb), 7 (PostgreSQL layouts) and 21.

### Source of the existing implementation

`gunstein/podman_test`, branch `feature/platform` (checked 2026-10-17 at
`5171197`), has a working DR design with a clean acceptance record:

- `deploy/dr/app_ops`: `python3 -m app_ops`, one command per DR operation, run
  from a controller over plain SSH (`BatchMode=yes`, pinned host keys,
  `sudo -n`), driven by a small YAML inventory of `primary`/`standby` hosts.
- `deploy/dr/app_dr_host`: building blocks staged on each host: streaming
  replication and its TLS, secret export/import between hosts, standby reseed,
  promoted application deploy and pair checks.
- `deploy/dr/scripts/app_dr.py` (fencing-gated promotion) and `app_backup.py`
  (physical base backup, WAL archive and point-in-time restore into disposable
  containers), plus systemd timers for a scheduled DR check and nightly backup.
- Commands such as `preflight-standby`, `bootstrap-standby`,
  `replication-status`, `failover --confirm-primary-fenced ...
  --confirm-promotion ...`, `deploy-promoted-application`, `configure-backup`
  and `rebuild-standby --confirm-fenced ... --confirm-reseed ...`.
- Boundaries: DR imports the single-host installer, never the reverse
  (`tests/test_dr_boundary.py`); every operation acts on one complete group of
  replicated databases and refuses a partial group; destructive steps need
  explicit confirmations; runbooks in `docs/runbooks/`.

### Differences to resolve in podman_offline

- Components and databases are declared per product (item 20), not a fixed
  todo/notes/keycloak group. The replicated set must come from declarations,
  for example an optional per-component DR declaration, and be recorded in
  installed metadata so the target knows it without the source checkout.
- Each component is a separate offline bundle with its own version and
  dependency checks; podman_test promotes one product bundle.
- Credentials here are files delivered as kube Secret YAML from component
  config directories, not `podman secret` objects; secret transfer to a
  standby must keep the credential-retention and logging contracts.
- Host constraints: Python 3.6 with PyYAML, no Jinja2, rootless user systemd,
  SELinux, fapolicyd trust per bundle, strictly offline targets.
- Existing safety guards must stay intact: database preflight, retry/pending
  state, scoped uninstall and `--delete-data`.

### DR must be optional

A single-host installation without DR must keep working exactly as today,
with no new requirement, service, timer, port or package. DR is enabled
explicitly, for example as a separate operations bundle and explicit
commands. Component bundles must not depend on DR code, and the deploy
package must never import DR code (add a boundary test). Disabling DR or
never enabling it must not leave replication slots, archive volumes or
timers behind.

### Phase 1: analysis and plan (deliver before implementing)

1. Read podman_test `feature/platform`: `deploy/dr/`, the installer's
   `backup.py`, `docs/runbooks/`, `docs/manual-recipes/03-DR-TWO-VM.md`,
   `04-BACKUP-PITR.md` and the acceptance record. List what can be reused
   unchanged, what must be adapted and what does not apply.
2. Propose a scope for the first delivery, for example: replication of
   declared PostgreSQL components to one standby, fencing-gated promotion,
   backup/PITR, and standby rebuild, with the rest deferred.
3. Propose the declaration schema, installed metadata, the operations
   package layout, the inventory format and the command list.
4. Describe the failure and retry model of every destructive step, and how
   each of the guide's contracts is preserved.
5. Plan the tests: unit tests with stubbed transport, harness tests, and the
   real two-VM acceptance scenarios with exact commands.
6. Get the user's approval of the plan before phase 2.

### Phase 2: implementation

- Develop on a separate branch, for example `feature/dr`, branched from
  `main` after item 20 has been merged.
- Deliver in reviewable steps that each keep the tests green: declarations
  and metadata, then replication, then promotion and fencing, then
  backup/PITR, then standby rebuild.
- Use a pull request to `main`. Open it as a draft early so the plan, the
  phased commits and the CI results are reviewed in one place; mark it ready
  only when the agreed scope, the tests and the real two-VM acceptance are
  complete. A pull request fits here because the change is large, touches
  safety-critical paths and needs review before it reaches `main`.

### Verification and delivery

Run product tests, acceptance-harness tests, ruff, format, pyright, vermin,
shellcheck and `git diff --check`. Add runnable real two-VM acceptance
scenarios (replication, fenced failover, promoted application access,
backup/PITR restore and standby rebuild) and document them even if no lab is
available; report unexecuted runtime scenarios as outstanding. Never count
podman_test's acceptance results as evidence for this repository.

## 25. Smaller follow-ups from the item 20 review

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md).

Status: planned. Found by the independent review of item 20 at `c00865f`;
none blocks the shipped demo. Handle each separately and keep them small.

- **F7, unfinished first install:** when a first install fails after its
  metadata is written but without pending owner work (for example at the
  component's own restart), `metadata/<id>.json` exists without
  `installed/<id>`. A retry of the same bundle completes it, but `uninstall`
  refuses with "not installed". Either let uninstall clean up such an
  unfinished install with its usual data rules, or document the retry as the
  only recovery and say so in the error. Add a fresh-process regression.
- **F8, application identity in three places:** `client.yaml` (`id`,
  `base_path`), the app's `APP_ID`/`BASE_PATH` environment and the route's
  `location` must agree, but nothing checks it; a mismatch shows up only as an
  OIDC failure. The generic tool must not learn the demo's environment names.
  Consider an optional check in the validation command of item 23 for products
  that declare which variables carry these values.
- **F10, demo provisioning in every bundle:** `bundle.py` copies the whole
  `scripts/` directory, so `scripts/generate-certificates.sh` ships in every
  product's bundles. Decide whether demo provisioning belongs in bundles at
  all, for example by shipping only `prepare-host.sh` and moving the demo
  script next to `dev/demo-credentials.sh`, and update the acceptance harness
  that runs it on the target.

## 26. Make reserved configuration names and shared settings visible

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: planned. Start after item 21. Requested 2026-10-17.

### Problem

All configuration values are written the same way in the same YAML files, but
some names have behavior built into the tools and others do not. Nothing in the
configuration shows which is which:

| Name | What the tools do with it |
| --- | --- |
| `PUBLIC_ORIGIN` | Validated as an HTTPS origin; copied from the `public_from` dependency at `init-config` and in dev; install refuses a mismatch; used for OIDC redirect URIs |
| `HTTPS_PORT` | Validated as a port 1-65535; inherited and compared like `PUBLIC_ORIGIN` |
| `PUBLIC_HOSTNAME` | Always derived from `PUBLIC_ORIGIN`; setting it is an error |
| `SECRET_FILES`, `VOLUME_FILES` | File-source declarations, not placeholder values |
| Any other name, e.g. `PUBLIC_MY_SETTING` | Only replaces `@@NAME@@`; each component keeps its own copy, nothing is inherited or compared, whatever its prefix |

So `PUBLIC_MY_SETTING` in `config/common.defaults.yaml` looks like
`PUBLIC_ORIGIN` but behaves differently: in production every component gets its
own copy at `init-config`, and a later edit in one component is neither
propagated nor detected. A product has no declarative way to share its own
value the way the gateway shares `PUBLIC_ORIGIN`.

Renaming the reserved names is not the goal: the tools must know what
`PUBLIC_ORIGIN` means to validate it, derive the hostname and build redirect
URIs, and a configurable name would only move the constant. The goal is that
the difference is visible and that products can share their own values.

### Message to the implementing agent

1. **Document the reserved names in one place.** Add a "Reserved configuration
   names" section to `docs/COMPONENTS.md` with the table above and the reason
   each is reserved. Link it from README's configuration section. Keep
   `deploy.PUBLIC_KEYS` and the documentation consistent, and say in a code
   comment where the documentation lives.
2. **Declare shared settings in the catalog.** Add one optional field on the
   component that owns the values, for example:

   ```yaml
   gateway:
     shares: [PUBLIC_MY_SETTING]
   ```

   A component with `public_from: gateway` then inherits and is compared on
   `PUBLIC_ORIGIN`, `HTTPS_PORT` and every name in the owner's `shares`, at
   `init-config`, in dev prepare and at install, exactly as `PUBLIC_ORIGIN` is
   today. `PUBLIC_ORIGIN` and `HTTPS_PORT` are always shared and keep their
   extra validation; listing them in `shares` is allowed but changes nothing.
   Validate names with the existing placeholder name rule and refuse reserved
   names that cannot be shared (`PUBLIC_HOSTNAME`, `SECRET_FILES`,
   `VOLUME_FILES`).
3. **Keep it offline and strict.** Compile `shares` into `bundle.yaml` and
   installed metadata, so a dependent's install compares against the owner's
   installed declaration without the source checkout. An owner upgrade that
   removes a shared name still used by an installed dependent must fail
   clearly before writes. Read installed metadata with the existing strictness;
   no migration or fallback (no installations of the old schema exist).
4. **Errors name the setting, both files and the declaring component**, never
   the values.

### Tests and delivery

Test inheritance at `init-config` and in dev, refusal of a mismatch at install
for a shared custom name, no comparison for unshared names, invalid and reserved
names in `shares`, an owner upgrade dropping a used name, and the renamed
product sharing a value from `gateway`. Run product tests, acceptance-harness
tests, ruff, format, pyright, vermin, shellcheck and `git diff --check`. Update
the review guide's contracts, `docs/COMPONENTS.md` and the release version.

## 27. Declare the product name instead of hardcoding `myproduct`

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: planned. Requested in the item 20 review (PR #1) on 2026-10-17. Start
after item 20 is merged and its acceptance runs are green.

### Problem

`myproduct` is the product name, not a component ID, and it predates item 20.
The code builds names from it in `deployment/` and `bundle.py`:
`myproduct-<id>.service`, the shared `myproduct.network`, Quadlet file names,
temporary-directory prefixes and archive names
(`myproduct-<id>-<version>-offline.tar.gz`). It is also fixed in `quadlet/`,
in `scripts/prepare-host.sh` (the `myproduct` service user and
`/var/lib/myproduct`), in the dev network and in the acceptance harness.

### Message to the implementing agent

1. Declare the product name once in `bundles.yaml`, for example
   `product: shop`, validated with the component ID rule. Compile it into every
   bundle descriptor and installed metadata, so the target needs no source.
2. Use it everywhere the code builds unit, network, Quadlet, temporary
   directory and archive names. Keep the standalone example mode working with
   an explicit name.
3. All components installed under one service user must share one product
   name; refuse a bundle with another name before any write.
4. Keep the host account and home (`prepare-host.sh`) as a separate, explicit
   setting rather than deriving them silently. Document both.
5. No migration of existing installations (none use another name); keep
   the demo name `myproduct`. Update the dev scripts and the acceptance harness
   to read the name instead of repeating it, and add a run with a different
   product name to the renamed-product scenario.

Run product tests, acceptance-harness tests, ruff, format, pyright, vermin,
shellcheck and `git diff --check`; report real acceptance runs separately.

## 28. Clarify the `install_standalone` docstring

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md).

Status: planned. Requested in the item 20 review (PR #1) on 2026-10-17. Small,
documentation only; can be done any time after item 20 is merged.

### Problem

`deployment/deploy.py` `install_standalone()` says only "Install a standalone
rootless manifest fixture using the persistent config." It does not say when it
is used instead of the component install (a release without `components/`), or
what it does, in this order (as of 0.4.10):

1. `production_environment()`; requires the service user's `~/config.yaml`
   (`common.HOME / "config.yaml"`, not `~/.config/...`), else "Missing ...".
2. `check_manifests()`: validates the effective `manifests/` (kinds,
   placeholders, pull policy, mounts, links), then the database preflight.
3. `render.materialize()`: generates allowed missing secrets and renders the
   YAML once, returning it with the import volumes; no files are written yet.
4. Requires `images/images.tar`, runs `podman load` and `podman image exists`
   for every image.
5. Only then writes the import archives to `files/`, so a failed image check
   never leaves new imports beside old YAML.
6. Writes the Quadlet `.yaml`, `.kube` and `.network`, then `daemon-reload`,
   `restart` and `is-active` for the single service, and `podman ps`.

Before 0.4.10 it rendered twice (without, then with archives) and ran the
database preflight only when the config existed.

### Task

Rewrite the docstring so a developer with some Python experience can tell from
it alone what the function is for, its inputs (`~/config.yaml`, `manifests/`,
`images/images.tar`), the order above, what it does not do (no catalog,
metadata, registrations, pending record or markers) and its failure cases. No behaviour change. Keep README's
standalone paragraph consistent.

## 29. fapolicyd denies systemd's Podman launch just after a trust update

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: planned; analyse before changing anything. Found in the item 20
acceptance run `decl-app1-first-2` (revision `8e62153`, 2026-10-17).

### Observation

Step `10-identity-install` (Identity 0.4.9 → 0.4.10) failed at
`systemctl --user restart myproduct-identity.service`. The release had been
added to the trust file, `fapolicyd-cli --update` had run and `wait_trust`
had confirmed every package file in the live database; validation,
`podman load` and the image checks had passed. About ten seconds after the
update, systemd's child for the unit was denied:

```text
syscall=execve exit=EPERM comm=(podman) exe=/usr/lib/systemd/systemd
FANOTIFY resp=deny fan_info=5 subj_trust=unknown obj_trust=yes
Failed at step EXEC spawning /usr/bin/podman: Operation not permitted (203/EXEC)
```

`/usr/bin/podman` is trusted (`obj_trust=yes`); the subject, a freshly forked
systemd process of the `myproduct` user manager, was not (`subj_trust=unknown`).
It was the only denial in the run. The same step passed in `decl-app2-first-2`
on the same revision, as did every other install, stop/start/restart, crash,
hang, reboot and upgrade restart in both runs. Earlier launcher denials
(`exe=systemd`, `comm=(podman)`, run-18) led to the `09-launch-audit-*` steps;
their cause was not established.

### Why it matters

The documented operator procedure does the same thing: add the release's trust,
`fapolicyd-cli --update`, then `./deploy install`, which restarts services. If
the denial is a window after a trust database reload, real installs and
upgrades can fail intermittently with 203/EXEC.

### Task

1. Reproduce: repeat trust add/update followed immediately by a user-unit
   restart on the lab PROD VM, and record how often and for how long after the
   update the denial occurs. Inspect the effective rule 5 (`fapolicyd-cli
   --list`), fapolicyd's version and its subject-trust handling for processes
   forked by `systemd --user` during a database reload.
2. Decide from evidence, not by weakening policy: candidates are waiting for a
   reliable "reload finished" condition before the restart, ordering the trust
   update earlier in the operator procedure, or one bounded, logged retry of a
   restart that fails with 203/EXEC and a matching denial. Never add trust
   rules, disable fapolicyd, or retry other failures.
3. If deploy code changes, keep the pending-owner semantics: a restart that
   still fails leaves the pending record for a later retry.
4. Add a focused acceptance check that installs right after a trust update and
   requires no FANOTIFY/AVC events; rerun `decl-app1-first`.

Run product tests, acceptance-harness tests, ruff, format, pyright, vermin,
shellcheck and `git diff --check`; report real acceptance runs separately.

## 30. Make the acceptance runs much faster

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: planned. Raised by the operator on 2026-10-17: the item 21 matrix (six
scenarios) took several hours, which is far too long.

### Where the time goes

Measured from the step tables of the item 20 runs on `8e62153`:

| Run | Total | Health waits (85–115 s steps) | Bundle builds (~263 s each) | Everything else |
| --- | ---: | ---: | ---: | ---: |
| `decl-app1-first-3` | 44 min | 15 steps, 24 min | 2 builds, 9 min | 11 min, including the 200 s hang test |
| `decl-renamed-4` | 27 min | 9 steps, 14 min | 2 builds, 9 min | 4 min |
| `decl-help-2` | 12 min | 2 steps, 3 min | 1 build, 4 min | 4 min |

1. **Health waits are more than half of every run.** Every container has
   `initialDelaySeconds: 90` and `periodSeconds: 30`, so after any install,
   start, restart, reboot or upgrade, `healthy` cannot pass in less than about
   90 seconds, even when everything is up in five. The hang test (200 s) is
   also derived from these numbers.
2. **Bundle builds take about 4.5 minutes each.** `build-bundle.sh` builds all
   five bundles, and `bundle.py` writes them with `tarfile` `w:gz`, which is
   single-threaded gzip at level 9. The upgrade steps rebuild every bundle to
   change one.
3. **The six scenarios repeat the same work.** Each one resets both VMs and
   rebuilds images, runs the unit suite and builds bundles from the same
   revision.

### Task

Measure first, on the lab VMs, then change in this order. Stop once the full
matrix is comfortably under an hour.

1. **Health timing (product decision, largest gain).** Check on Podman 5.8.2
   what `kube play` does with `startupProbe` and with a shorter
   `initialDelaySeconds`: when the status becomes `healthy`, and how a hung
   container is detected. Then propose one of these to the operator, with
   measured times:
   - a `startupProbe` with a short period and a generous total budget (slow
     first starts such as Identity and PostgreSQL initialization keep their
     time), plus a liveness probe without a long initial delay
   - or a shorter `initialDelaySeconds` and period

   This changes the documented product contract (README "Health checks and
   acceptance", `tests/test_health.py`, the VM checklist and the hang-test
   limit), so it needs the operator's approval before it changes.
2. **Bundle builds.** Time `podman save` against compression separately. Then
   consider a lower gzip level or a faster compressor available on the build
   host, and building only the changed component in the upgrade steps. The
   archive format and checksums must stay the same for the target.
3. **Repeated work across scenarios.** Consider a matrix mode that builds
   images, the unit suite and bundles once per revision and reuses them,
   checked by hash, in each scenario. This conflicts with the current rule
   that every clean run builds from source, so weigh it last and keep single
   scenarios unchanged.
4. Record before and after times per scenario in the acceptance README, and
   keep every check that exists today. Speed must not come from dropping
   evidence.
