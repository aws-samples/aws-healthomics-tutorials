// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models.exceptions

class VincentInternalException(
    private val message: String = "",
    private val cause: Throwable = None.orNull)
    extends RuntimeException(message, cause)
