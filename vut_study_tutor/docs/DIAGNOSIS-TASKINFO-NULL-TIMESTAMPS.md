# Diagnóza – nulové hodnoty `Get-ScheduledTaskInfo`

## Symptom

```text
Get-TaskDiagnostic : You cannot call a method on a null-valued expression.
FullyQualifiedErrorId: InvokeMethodOnNull,Get-TaskDiagnostic
```

## Příčina

Task Scheduler vrátil objekt task-info, ale nejméně jedna z vlastností
`LastRunTime` nebo `NextRunTime` měla hodnotu `$null`. Adaptér 2.1.2 kontroloval
jen `$info -ne $null` a následně volal `$info.LastRunTime.ToString('o')` a
`$info.NextRunTime.ToString('o')`.

## Oprava

Adaptér 2.1.4 deleguje sestavení diagnostického záznamu do čisté funkce
`New-TaskDiagnosticRecord`. Každá vlastnost se načítá přes bezpečný property
lookup a čas se formátuje výhradně funkcí `ConvertTo-TaskDateTimeText`, která
podporuje `$null`, chybějící vlastnost, `DateTime`, `DateTimeOffset` i textovou
náhradní hodnotu.

Stejná oprava je použita v `collect-vut-ai-tutor-einfra-diagnostics-v2.1.4.ps1`.
Offline `-Action SelfTest` vytváří přesně syntetický task-info objekt s nulovými
časovými vlastnostmi, takže opakování chyby zablokuje vydání ještě před prací s
produkčním Task Schedulerem.
