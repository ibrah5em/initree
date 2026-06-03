FROM ${runtime.base_image} AS build
WORKDIR /src
COPY go.mod ./
RUN ${runtime.install_cmd}
COPY . .
RUN ${runtime.build_cmd}

FROM ${runtime.run_base_image}
COPY --from=build ${runtime.artifact} /server
EXPOSE ${app.port}
ENTRYPOINT ["${app.start_command}"]
