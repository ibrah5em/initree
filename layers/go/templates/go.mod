module ${project.slug}

go ${runtime.version}

require (
    // >>> initree:inject runtime.dependencies
    // <<< initree:inject runtime.dependencies
)
