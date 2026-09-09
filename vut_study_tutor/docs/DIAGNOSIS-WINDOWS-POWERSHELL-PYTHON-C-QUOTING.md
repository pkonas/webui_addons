# Diagnóza – Windows PowerShell 5.1 odstranil uvozovky z `python -c`

## Symptom

```text
File "<string>", line 1
  import sys; print(..join(map(str,sys.version_info[:3])))
                    ^
SyntaxError: invalid syntax
```

## Příčina

Test 2.1.3 volal CPython přes přímý nativní příkaz PowerShellu a předával
inline argument s vnořenými uvozovkami. Windows PowerShell 5.1 používá legacy
rekonstrukci nativního příkazového řádku; v tomto hostiteli vnitřní uvozovky
nepřežily a Python obdržel `..join` namísto `".".join`.

## Oprava

Adaptér 2.1.4 nepředává first-party Python zdroje přes `-c`. Host probe i
SQLite self-test jsou skutečné dočasné nebo balíčkové `.py` soubory. Na
command line se předávají pouze cesta skriptu a datové argumenty, takže
výsledek není závislý na pravidlech vnořených uvozovek Windows PowerShell 5.1.

Regresní test odmítá v first-party PowerShell souborech jak přímý tvar
`& $python -c ...`, tak argumentové pole začínající `@('-c', ...)`.
