// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.vcf

case class VCFAnnotationOptions(
    ignoreQualField: Option[Boolean],
    ignoreFilterField: Option[Boolean])
