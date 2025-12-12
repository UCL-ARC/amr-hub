# CADFlow

**CADFlow** is a containerised workflow for converting AutoCAD **DWG** drawings
into geospatial **GeoPackage (GPKG)** files suitable for GIS and spatial
analysis.
The system runs entirely in Docker and performs batch processing through two
stages:

1. **Converter**: runs the ODA File Converter headlessly to produce `.dxf`.
2. **Processor**: converts `.dxf` into `.gpkg` using `dxf2geo` and configurable
   filter rules.

All input, intermediate, and output artefacts are handled via bind-mounted
directories.
Each drawing can be processed with drawing-specific configuration supplied as
YAML files under `config/`.

---

## Data Flow

> in/ ──► [converter] ──► work/ ──► [processor] ──► out/

- **in/**: Input DWG files.
- **work/**: Intermediate DXF files.
- **out/**: Final GeoPackages.
- **config/**: Optional per-drawing YAML configs controlling extraction rules.

Each DWG produces **one GPKG** in `out/`, named after the input stem.

---

## Building

CADFlow uses **Docker Buildx** to produce the converter and processor images.
The Makefile provides targets for initialising the Buildx environment and
building the images.

### Initialise Buildx (required once per machine)

```bash
make builder-init
```

This performs:

- Installation of platform emulators (`binfmt`) for multi-arch support.
- Creation of a Buildx builder instance.
- Activation and bootstrapping of the builder.

### Re-activate Buildx in a new shell

```bash
make builder-use
```

### Build all images

```bash
make build-all
```

Or build individual stages:

```bash
make build-converter
make build-processor
```

All images are loaded into the local Docker daemon and are immediately runnable.

---

## Running the pipeline

### Prepare directories

```bash
make dirs
```

This creates `in/`, `work/`, and `out/`.

### Add DWG files

Place input drawings in:

> in/

### Execute the full conversion pipeline

```bash
docker compose up
```

or

```bash
make up
```

The converter outputs `.dxf` files to `work/`.
The processor detects `.dxf` files, loads the appropriate filter config from
`config/`, and writes one `.gpkg` per drawing into `out/`.

---

### Execute the pipeline stage by stage

```bash
make run-converter
make run-processor
```

---

## Cleaning and Maintenance

### Clean pipeline artefacts

```bash
make clean
```

This removes:

- The running Compose stack
- Converter and processor images
- Any BuildKit containers spawned by Buildx

### Remove all non-default Buildx builders

```bash
make clean-builders
```

This deletes:

- All custom Buildx builders
- Stale BuildKit containers
- Unused Docker networks

Useful when Buildx becomes inconsistent.

### Aggressively prune Docker

```bash
make clean-cache
```

Runs:

```bash
docker system prune -a -f --volumes
```

This removes all unused images, caches, containers, networks, and volumes
system-wide.

---

## Configuration

YAML files under `config/` control the extraction rules for each drawing.

The processor resolves configuration as follows:

1. `config/<drawing_stem>.yml`
2. `config/<drawing_stem>.yaml`
3. `config/default_filters.yml`
4. `config/blank_filters.yml`

These files define:

- Layer include rules
- Layer exclude rules
- Field-based exclusions
- Optional CRS assumptions

No examples are included here, as configurations may encode proprietary or
drawing-specific logic.

If no suitable config is found, the blank configuration is used.

---

## Exit Codes

| Code | Meaning                                       |
| ---- | --------------------------------------------- |
| 0    | Successful execution                          |
| 1    | Failure inside the processor code             |
| 2    | No matching DWG or DXF files found            |
| 143  | Process terminated by SIGTERM (external stop) |

Exit code **143** indicates the container was stopped externally (Compose stop,
Ctrl+C, or `--abort-on-container-exit` behaviour).

---

## Directory Layout

```text
cadflow/
├── converter/
│   ├── Dockerfile
│   └── run_convert.sh
├── processor/
│   ├── Dockerfile
│   ├── run_conversion.py
│   ├── run_process.sh
│   └── utils.py
├── config/
│   ├── default_filters.yml          (optional)
│   ├── blank_filters.yml            (optional)
│   └── <drawing_name>.yml           (optional per-drawing)
├── in/
├── work/
├── out/
└── Makefile
```

## Dependencies

The CADFlow workflow is fully containerised, and all Python-level dependencies
are installed inside the Docker images during the build process.
Only a small set of external tools is required on the host machine in order to
build and run the pipeline.

### Required on the Host

#### Docker Engine

A recent version of Docker CE or Docker Desktop is required.
The system relies on Docker for:

- Building the converter and processor images
- Running isolated containers for each processing stage
- Mounting `in/`, `work/`, `out/`, and `config/` directories
- Managing image caches and container networks

Any host capable of running Docker can execute the full workflow without
installing Python, GDAL, or ODA tooling locally.

#### Docker Buildx

Buildx is used for image builds. It provides:

- A modern BuildKit-based backend
- Cross-platform build support (required for the converter image)
- Support for `--load` so images are placed directly into the local Docker
  daemon

The Makefile includes dedicated targets (`builder-init`, `builder-use`) to
configure Buildx automatically.

#### binfmt (QEMU multi-arch support)

Installed automatically by the Makefile via:

```bash
docker run --rm --privileged tonistiigi/binfmt --install all
```

This enables the host to execute foreign-architecture binaries during image
builds where required.

### Not Required on the Host

The following **do not** need to be installed locally:

- Python or any Python libraries
- GDAL / OGR tooling
- dxf2geo or its dependencies
- ODA File Converter
- Any GIS-related software

All of these are isolated within the container images.

### Optional but Useful

- **Docker Compose v2** (bundled with modern Docker installations): Used to
  orchestrate the converter and processor containers in sequence.

In summary, the only host-level requirements for running CADFlow are:

- Docker
- Docker Buildx
- binfmt support (automatically configured)

Everything else is encapsulated in the container images for portability and reproducibility.

## Contact

- Keiran Suchak ([k.suchak@leeds.ac.uk](mailto:k.suchak@leeds.ac.uk))
