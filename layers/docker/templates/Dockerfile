# syntax=docker/dockerfile:1
# initree:if runtime.build_cmd
# Compiled language: build the artifact in a full toolchain image, ship it on a minimal base.
FROM ${runtime.base_image} AS build
WORKDIR /src
COPY . .
RUN ${runtime.install_cmd}
RUN ${runtime.build_cmd}

FROM ${runtime.run_base_image}
COPY --from=build ${runtime.artifact} /server
EXPOSE ${app.port}
ENTRYPOINT ["${app.start_command}"]
# initree:else
FROM ${runtime.base_image}

WORKDIR /app

${runtime.image_prep}

COPY . .
RUN ${runtime.install_cmd}

EXPOSE ${app.port}
CMD ${app.start_command}
# initree:endif
