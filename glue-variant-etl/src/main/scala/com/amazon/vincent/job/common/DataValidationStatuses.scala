// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.common

object DataValidationStatuses extends Enumeration {
  type DataValidationStatus = Value

  val PASS, FAIL_PARTIAL_WRITE = Value
}
