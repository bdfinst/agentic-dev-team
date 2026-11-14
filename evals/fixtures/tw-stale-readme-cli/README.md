# logship

logship forwards log files to a central collector.

## Install

```bash
pip install logship
```

## Usage

```bash
logship --out tcp://logs.example.com /var/log/app/*.log
```

## Options

| Flag | Default | Description |
|---|---|---|
| `--out` | (required) | Collector URL |
| `--port` | `5140` | Collector port |
| `--verbose`, `-v` | off | Print every line sent |
| `--batch-size` | `200` | Lines per send |

## License

MIT
