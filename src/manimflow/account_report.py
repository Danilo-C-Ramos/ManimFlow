"""What `manimflow account` reports: how ManimFlow is signed in to Codex, the ChatGPT
plan, the models the account's catalog offers and which one the switch uses."""

from dataclasses import asdict, dataclass, field

from manimflow.agent import Account, Agent, ModelOption, ModelSettings, QuotaWindow
from manimflow.model_presets import CAREFUL, QUICK

NOT_SIGNED_IN = "O ManimFlow não está conectado. Abra o app e entre com o ChatGPT ou com uma chave de API."


@dataclass
class AccountReport:
    account: Account
    presets: dict[str, ModelSettings]
    models: list[ModelOption]
    # None without a ChatGPT plan, as with an API key.
    quota: list[QuotaWindow] | None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "command": "account",
            "account": asdict(self.account),
            "presets": {name: asdict(settings) for name, settings in self.presets.items()},
            "models": [asdict(option) for option in self.models],
            "quota": None
            if self.quota is None
            else [
                {
                    "used_percent": window.used_percent,
                    "minutes": window.minutes,
                    "resets_at": window.resets_at.isoformat() if window.resets_at else None,
                }
                for window in self.quota
            ],
            "errors": self.errors,
        }

    def lines(self) -> list[str]:
        """The report as text, in Portuguese like the rest of what the teacher reads."""
        account = self.account
        match account.method:
            case "chatgpt":
                plan = f", plano {account.plan}" if account.plan else ""
                email = f" ({account.email})" if account.email else ""
                lines = [f"Conta: ChatGPT{plan}{email}"]
            case "api_key":
                lines = ["Conta: chave de API da OpenAI"]
            case _:
                lines = ["Conta: conectado" if account.logged_in else "Conta: não conectado"]
        lines += [f"{name}: {self.presets[name].model}, esforço {self.presets[name].effort}" for name in (QUICK, CAREFUL)]
        lines.append("Modelos do catálogo da conta (* o padrão do Codex):")
        width = max((len(option.model) for option in self.models), default=0)
        lines += [
            f"  {'*' if option.default else ' '} {option.model:<{width}}  {option.name}: "
            f"{', '.join(option.efforts)} (padrão {option.default_effort})"
            for option in self.models
        ]
        for window in self.quota or []:
            limit = f"janela de {window.minutes} min" if window.minutes else "limite de uso"
            resets = f", renova em {window.resets_at.astimezone():%d/%m %H:%M}" if window.resets_at else ""
            lines.append(f"Uso do plano: {window.used_percent}% ({limit}{resets})")
        return lines


async def read_account(agent: Agent) -> AccountReport:
    account = await agent.account()
    report = AccountReport(account, await agent.presets(), await agent.models(), await agent.quota())
    if not account.logged_in:
        report.errors.append(NOT_SIGNED_IN)
    return report
