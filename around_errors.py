"""Keep only the lines around the errors, so the log fits in one call."""


def around_errors(lines, n=20):
    keep = set()
    for i, line in enumerate(lines):
        if " ERROR " in line or line.startswith("Traceback"):
            keep.update(range(max(0, i - n), min(len(lines), i + n + 1)))
    out, last = [], -1
    for i in sorted(keep):
        if i != last + 1:
            out.append("...")
        out.append(lines[i])
        last = i
    return "\n".join(out)


if __name__ == "__main__":
    lines = open("logs/sorrel-incident.log").read().splitlines()
    print(around_errors(lines))
