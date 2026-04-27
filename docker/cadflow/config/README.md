# CADFlow configuration

## ODA File Converter package

`oda.env` controls which ODA File Converter package is used when building the
converter image.

```dotenv
ODA_VER=27.1
ODA_DEB_URL=
ODA_SHA256=
```

- `ODA_VER` is used to construct the standard ODA guestfiles URL.
- `ODA_DEB_URL` overrides the constructed URL when set.
- `ODA_SHA256` is optional, but should be set for reproducible builds.

The standard URL pattern is:

```text
https://www.opendesign.com/guestfiles/get?filename=ODAFileConverter_QT6_lnxX64_8.3dll_${ODA_VER}.deb
```

Update `ODA_VER` when ODA publishes a newer package. If ODA changes its filename
pattern, leave `ODA_VER` as documentation and set `ODA_DEB_URL` explicitly.

## Drawing filters

Drawing-specific processor configuration can also be placed in this directory:

1. `<drawing_stem>.yml`
2. `<drawing_stem>.yaml`
3. `default_filters.yml`
4. `blank_filters.yml`
