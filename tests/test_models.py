from three_layer_installer import models


def test_stack_has_exactly_three_layers() -> None:
    assert [(layer.value, layer.label) for layer in models.Layer] == [
        (1, "RTK"),
        (2, "Native LSP"),
        (3, "jMunch"),
    ]


def test_status_values_do_not_overstate_activation() -> None:
    assert {status.value for status in models.Status} == {
        "ACTIVE",
        "CONFIGURED",
        "GUIDANCE ONLY",
        "EXPERIMENTAL",
        "UNAVAILABLE FROM CLIENT",
        "SKIPPED",
        "FAILED",
    }


def test_jmunch_use_has_no_implicit_default() -> None:
    assert {basis.value for basis in models.JMunchUse} == {
        "noncommercial",
        "commercial-licensed",
        "skip",
    }


def test_layer_result_keeps_component_detail() -> None:
    result = models.LayerResult(
        client=models.ClientId.CLAUDE,
        layer=models.Layer.JMUNCH,
        status=models.Status.FAILED,
        message="one component failed",
        components={"jcodemunch": models.Status.ACTIVE, "jdocmunch": models.Status.FAILED},
        verification_scope=models.VerificationScope.SERVER_PROTOCOL,
    )

    assert result.components["jdocmunch"] is models.Status.FAILED
    assert result.verification_scope is models.VerificationScope.SERVER_PROTOCOL

