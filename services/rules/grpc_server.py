"""gRPC endpoint stub. Generate pb2 modules from contracts/rules.proto."""
import grpc
import rules_pb2
import rules_pb2_grpc


class RulesEngineServicer(rules_pb2_grpc.RulesEngineServicer):
    async def EvaluateCheck(
        self, request: rules_pb2.CheckRequest, context: grpc.aio.ServicerContext
    ) -> rules_pb2.CheckDecision:
        ...


async def serve_grpc() -> None:
    ...
