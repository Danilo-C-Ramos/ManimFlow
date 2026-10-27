from manimflow.agent import AgentError, AssistantText, CommandFinished, CommandStarted, FileChanged
from manimflow.fake_agent import EditFile, Produce, ScriptedAgent


async def collect(stream):
    return [event async for event in stream]


async def test_replays_each_turn_and_applies_its_file_edits(tmp_path):
    agent = ScriptedAgent(
        [
            [
                AssistantText("Vou trocar a cor da luz."),
                CommandStarted("1", "manimflow preview . S2"),
                EditFile("cenas.py", "COR_LUZ = AMARELO\n"),
                CommandFinished("1", "manimflow preview . S2", 0),
            ],
            [AssistantText("Pronto.")],
        ]
    )
    session = await agent.start_session(tmp_path)

    first = await collect(session.send("muda a cor da luz"))
    second = await collect(session.send("obrigado"))

    assert first == [
        AssistantText("Vou trocar a cor da luz."),
        CommandStarted("1", "manimflow preview . S2"),
        FileChanged("cenas.py", "added"),
        CommandFinished("1", "manimflow preview . S2", 0),
    ]
    assert (tmp_path / "cenas.py").read_text(encoding="utf-8") == "COR_LUZ = AMARELO\n"
    assert second == [AssistantText("Pronto.")]


async def test_editing_an_existing_file_reports_a_modification(tmp_path):
    (tmp_path / "cenas.py").write_text("antes\n", encoding="utf-8")
    agent = ScriptedAgent([[EditFile("cenas.py", "depois\n")]])
    session = await agent.start_session(tmp_path)

    events = await collect(session.send("muda"))

    assert events == [FileChanged("cenas.py", "modified")]
    assert (tmp_path / "cenas.py").read_text(encoding="utf-8") == "depois\n"


async def test_a_command_s_output_is_written_without_reporting_a_file_change(tmp_path):
    agent = ScriptedAgent(
        [
            [
                CommandStarted("1", "manimflow preview . S0"),
                Produce("saida/previa/png/S0.png", b"\x89PNG"),
                CommandFinished("1", "manimflow preview . S0", 0),
            ]
        ]
    )
    session = await agent.start_session(tmp_path)

    events = await collect(session.send("renderiza"))

    assert events == [
        CommandStarted("1", "manimflow preview . S0"),
        CommandFinished("1", "manimflow preview . S0", 0),
    ]
    assert (tmp_path / "saida/previa/png/S0.png").read_bytes() == b"\x89PNG"


async def test_reports_an_error_when_the_scenario_runs_out(tmp_path):
    agent = ScriptedAgent([[AssistantText("Oi.")]])
    session = await agent.start_session(tmp_path)
    await collect(session.send("oi"))

    events = await collect(session.send("e agora?"))

    assert len(events) == 1
    assert isinstance(events[0], AgentError)
